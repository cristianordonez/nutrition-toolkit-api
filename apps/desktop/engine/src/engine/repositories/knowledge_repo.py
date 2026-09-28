"""Storage and retrieval for the diet and nutrition-care manuals.

One repository for both halves. The server split them -- writes here, search in
``embedding_repo`` -- which meant the two sides could disagree about which
model a stored vector came from, and nothing owned keeping the search index in
step with the rows it indexes. Here they are the same object: ingesting chunks
and searching them share `self.model`, and a write that invalidates the index
is the same call that repairs it.

Chunk vectors live directly in the Alembic-managed ``knowledge_chunk_vector``
vec0 table. A manual filter is applied inside vec0 before ranking --
the agent has one tool per manual, and filtering afterwards would let the
other manual's passages eat the ``k`` slots before the right ones were
considered.
"""

from __future__ import annotations

import logging
import typing
from hashlib import sha256

from sqlalchemy import insert
from sqlalchemy import select as sql_select
from sqlmodel import col, delete, select

from engine.database.vectors import knowledge_vectors, pack_embedding
from engine.models.clinical_facts import utc_now
from engine.models.rag import RagSearchMatch
from engine.models.sql.knowledge import (
    Knowledge,
    KnowledgeChunk,
)
from engine.utils.misc import require_id

if typing.TYPE_CHECKING:
    import pathlib
    from collections.abc import Sequence

    from sqlmodel import Session

    from engine.models.knowledge import KnowledgeChunkCreate
    from engine.models.sql.knowledge import KnowledgeType

logger = logging.getLogger(__name__)


class KnowledgeRepo:
    """Store manual chunks and search them by similarity."""

    def __init__(self, session: Session, model: str) -> None:
        """Bind to one embedding model.

        A vector is only comparable to others from the model that produced
        it. Holding the model here is what stops an ingest writing vectors
        the search will never look at.
        """
        self.session = session
        self.model = model

    # ------------------------------------------------------------------ write

    def create_knowledge(
        self,
        path: pathlib.Path,
        knowledge_type: KnowledgeType,
    ) -> Knowledge:
        """Create the persisted identity for one manual file."""
        return Knowledge(
            filename=path.name,
            knowledge_type=knowledge_type,
            file_hash=sha256(path.read_bytes()).hexdigest(),
        )

    def find_existing_knowledge(
        self,
        knowledge_type: KnowledgeType,
        file_hash: str,
    ) -> Knowledge | None:
        """Find a manual that has already been ingested, by content hash."""
        return self.session.exec(
            select(Knowledge).where(
                Knowledge.knowledge_type == knowledge_type,
                Knowledge.file_hash == file_hash,
            ),
        ).first()

    def ingest(
        self,
        knowledge: Knowledge,
        chunks: Sequence[KnowledgeChunkCreate],
        embeddings: Sequence[list[float]],
        *,
        overwrite: bool = False,
    ) -> Knowledge:
        """Store one manual's chunks and their vectors, then index them.

        Re-ingesting the same file is a no-op unless ``overwrite`` is set:
        identity is the content hash, so a manual that has not changed does
        not get chunked and embedded again.
        """
        self._validate(chunks, embeddings)
        packed = [pack_embedding(embedding) for embedding in embeddings]
        existing = self.find_existing_knowledge(
            knowledge.knowledge_type,
            knowledge.file_hash,
        )
        if existing is not None and not overwrite:
            logger.info(
                "Manual already ingested; skipping %s",
                knowledge.filename,
            )
            return existing
        if existing is not None:
            self._delete_chunks(require_id(existing.id))
            existing.filename = knowledge.filename
            existing.synced_at = utc_now()
            knowledge = existing
        self.session.add(knowledge)
        self.session.flush()
        chunk_models = [
            KnowledgeChunk(
                knowledge_id=require_id(knowledge.id),
                chunk_index=index,
                content=chunk.content,
                section_title=chunk.section_title,
                source_page_start=chunk.source_page_start,
                source_page_end=chunk.source_page_end,
            )
            for index, chunk in enumerate(chunks)
        ]
        self.session.add_all(chunk_models)
        self.session.flush()
        if chunk_models:
            self.session.exec(
                insert(knowledge_vectors),
                params=[
                    {
                        "knowledge_chunk_id": require_id(chunk.id),
                        "model": self.model,
                        "embedding": embedding,
                    }
                    for chunk, embedding in zip(chunk_models, packed, strict=True)
                ],
            )
        self.session.commit()
        self.session.refresh(knowledge, attribute_names=["chunks"])
        return knowledge

    def count_chunks(self, knowledge_id: int) -> int:
        """Return how many chunks are stored for one manual."""
        return len(
            self.session.exec(
                select(KnowledgeChunk.id).where(
                    KnowledgeChunk.knowledge_id == knowledge_id,
                ),
            ).all(),
        )

    # ------------------------------------------------------------------- read

    def search(
        self,
        query_vector: list[float],
        top_k: int,
        *,
        knowledge_type: KnowledgeType | None = None,
    ) -> list[RagSearchMatch]:
        """Return the manual passages nearest ``query_vector``, best first."""
        if top_k < 1:
            msg = "top_k must be positive"
            raise ValueError(msg)
        if not any(query_vector):
            return []
        candidates = select(KnowledgeChunk.id).join(Knowledge)
        if knowledge_type is not None:
            candidates = candidates.where(Knowledge.knowledge_type == knowledge_type)
        nearest = (
            sql_select(
                knowledge_vectors.c.knowledge_chunk_id,
                knowledge_vectors.c.distance,
            )
            .where(
                knowledge_vectors.c.embedding.op("MATCH")(pack_embedding(query_vector)),
            )
            .where(knowledge_vectors.c.model == self.model)
            .where(knowledge_vectors.c.knowledge_chunk_id.in_(candidates))
            .where(knowledge_vectors.c.k == top_k)
            .cte("nearest")
        )
        statement = (
            select(KnowledgeChunk, Knowledge, nearest.c.distance)
            .join(
                nearest,
                nearest.c.knowledge_chunk_id == col(KnowledgeChunk.id),
            )
            .join(Knowledge, col(KnowledgeChunk.knowledge_id) == col(Knowledge.id))
            .order_by(nearest.c.distance)
        )
        return [
            RagSearchMatch(
                document_id=require_id(knowledge.id),
                filename=knowledge.filename,
                chunk_text=chunk.content,
                similarity=1.0 - distance,
                knowledge_type=knowledge.knowledge_type,
                section_title=chunk.section_title,
                source_page_start=chunk.source_page_start,
                source_page_end=chunk.source_page_end,
            )
            for chunk, knowledge, distance in self.session.exec(statement).all()
        ]

    # ---------------------------------------------------------------- private

    def _delete_chunks(self, knowledge_id: int) -> None:
        """Drop one manual's chunks; migration triggers delete their vectors."""
        self.session.exec(
            delete(KnowledgeChunk).where(
                col(KnowledgeChunk.knowledge_id) == knowledge_id,
            ),
        )

    @staticmethod
    def _validate(
        chunks: Sequence[KnowledgeChunkCreate],
        embeddings: Sequence[list[float]],
    ) -> None:
        """Refuse a batch whose chunks and vectors do not line up.

        The server also required an embedding model name here. It is no longer
        a parameter: the repository is constructed with the model it indexes
        under, so a caller cannot label vectors with one model and have them
        searched as another.
        """
        if len(chunks) != len(embeddings):
            msg = "Each knowledge chunk must have one embedding"
            raise ValueError(msg)


__all__ = ["KnowledgeRepo"]
