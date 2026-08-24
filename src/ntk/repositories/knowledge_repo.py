"""Persistence operations for knowledge documents and their chunks."""

from __future__ import annotations

import logging
import typing
from datetime import UTC, datetime
from hashlib import sha256

from pydantic import TypeAdapter
from sqlmodel import Session, col, delete, select

from ntk.models.sql.knowledge import (
    Knowledge,
    KnowledgeChunk,
    KnowledgeChunkEmbedding,
)

if typing.TYPE_CHECKING:
    import pathlib
    from collections.abc import Sequence
    from uuid import UUID

    from ntk.models.knowledge import KnowledgeType

logger = logging.getLogger(__name__)
_METADATA_ADAPTER = TypeAdapter(dict[str, object])


class KnowledgeRepo:
    """Store knowledge sources, chunks, and chunk embeddings."""

    def __init__(self, session: Session) -> None:
        """Initialize the repository with a database session."""
        self.session = session

    def ingest(
        self,
        knowledge: Knowledge,
        chunks: Sequence[str],
        embeddings: Sequence[list[float]],
        model_name: str | None,
        *,
        overwrite: bool = False,
    ) -> Knowledge:
        """Store a knowledge document and replace its chunks when requested."""
        self._validate(chunks, embeddings, model_name)
        existing = self.find_existing_knowledge(
            knowledge.knowledge_type,
            knowledge.file_hash,
        )
        if existing is not None and not overwrite:
            logger.info(
                "Knowledge source already ingested; skipping %s",
                knowledge.filename,
            )
            return existing
        if existing is not None:
            self._delete_chunks(existing.id)
            existing.filename = knowledge.filename
            existing.synced_at = datetime.now(UTC)
            knowledge = existing
        self.session.add(knowledge)
        self.session.flush()
        chunk_models = self.create_knowledge_chunks(knowledge, chunks)
        self.session.add_all(chunk_models)
        self.session.flush()
        embedding_models = self.create_chunk_embedding(
            chunk_models, embeddings, model_name
        )
        self.session.add_all(embedding_models)
        self.session.commit()
        self.session.refresh(knowledge, attribute_names=["chunks"])
        return knowledge

    def create_chunk_embedding(
        self,
        chunk_models: list[KnowledgeChunk],
        embeddings: Sequence[list[float]],
        model_name: str | None,
    ) -> list[KnowledgeChunkEmbedding]:
        """Create chunk embedding models.

        :param chunk_models: List of KnowledgeChunk models
        :param embeddings: list of embedding floats
        :param model_name: LLM model used to create embeddings
        :return: KnowledgeChunkEmbedding models
        """
        return [
            KnowledgeChunkEmbedding(
                knowledge_chunk_id=chunk.id,
                embedding_vector=embedding,
                model_name=model_name or "",
            )
            for chunk, embedding in zip(chunk_models, embeddings, strict=True)
        ]

    def create_knowledge_chunks(
        self,
        knowledge: Knowledge,
        chunks: Sequence[str],
    ) -> list[KnowledgeChunk]:
        """Create knowledge chunk models.

        :param knowledge: Knowledge model
        :param chunks: list of chunks
        :return: KnowledgeChunk list
        """
        return [
            KnowledgeChunk(
                knowledge_id=knowledge.id,
                chunk_index=i,
                content=chunk,
            )
            for i, chunk in enumerate(chunks)
        ]

    def find_existing_knowledge(
        self,
        knowledge_type: KnowledgeType,
        file_hash: str,
    ) -> Knowledge | None:
        """Find a knowledge source that has already been ingested."""
        return self.session.exec(
            select(Knowledge).where(
                Knowledge.knowledge_type == knowledge_type,
                Knowledge.file_hash == file_hash,
            ),
        ).first()

    def create_knowledge(
        self,
        path: pathlib.Path,
        knowledge_type: KnowledgeType,
    ) -> Knowledge:
        """Create the persisted identity for this knowledge document."""
        return Knowledge(
            filename=path.name,
            knowledge_type=knowledge_type,
            file_hash=sha256(path.read_bytes()).hexdigest(),
        )

    def count_chunks(self, document_id: UUID) -> int:
        """Return the number of chunks stored for a knowledge source."""
        return len(
            self.session.exec(
                select(KnowledgeChunk.id).where(
                    KnowledgeChunk.knowledge_id == document_id,
                ),
            ).all(),
        )

    def _delete_chunks(self, knowledge_id: UUID) -> None:
        chunk_ids = self.session.exec(
            select(KnowledgeChunk.id).where(
                KnowledgeChunk.knowledge_id == knowledge_id,
            ),
        ).all()
        if chunk_ids:
            self.session.exec(
                delete(KnowledgeChunkEmbedding).where(
                    col(KnowledgeChunkEmbedding.knowledge_chunk_id).in_(chunk_ids),
                ),
            )
        self.session.exec(
            delete(KnowledgeChunk).where(
                col(KnowledgeChunk.knowledge_id) == knowledge_id,
            ),
        )

    @staticmethod
    def _validate(
        chunks: Sequence[str],
        embeddings: Sequence[list[float]],
        model_name: str | None,
    ) -> None:
        if len(chunks) != len(embeddings):
            msg = "Each knowledge chunk must have one embedding"
            raise ValueError(msg)
        if chunks and not model_name:
            msg = "Embedding model name is required"
            raise ValueError(msg)
