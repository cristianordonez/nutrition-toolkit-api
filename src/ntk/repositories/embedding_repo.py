"""Vector-search persistence operations."""

from __future__ import annotations

import typing

from sqlalchemy import text

from ntk.models.knowledge import KnowledgeType
from ntk.models.rag import RagSearchMatch
from ntk.models.sql.resident import StatusType

if typing.TYPE_CHECKING:
    from sqlmodel import Session

_ASSESSMENT_SEARCH_SQL = """
    SELECT a.id, a.source_filename, a.content,
           1 - (e.embedding_vector <=> CAST(:vector AS vector)) AS similarity
    FROM resident_assessment_embeddings e
    JOIN resident_assessment a ON a.id = e.resident_assessment_id
    WHERE a.status = :finalized_status
    ORDER BY e.embedding_vector <=> CAST(:vector AS vector)
    LIMIT :top_k
"""

_KNOWLEDGE_SEARCH_SQL = """
    SELECT k.id, k.filename, c.content,
           1 - (e.embedding_vector <=> CAST(:vector AS vector)) AS similarity
    FROM knowledge_chunks_embeddings e
    JOIN knowledge_chunks c ON c.id = e.knowledge_chunk_id
    JOIN knowledge k ON k.id = c.knowledge_id
    WHERE k.knowledge_type IN (:diet_manual, :nutrition_manual)
    ORDER BY e.embedding_vector <=> CAST(:vector AS vector)
    LIMIT :top_k
"""


class EmbeddingRepo:
    """Search stored assessment and knowledge vectors using one session."""

    def __init__(self, session: Session) -> None:
        """Store the controller-owned session."""
        self.session = session

    def search_assessments(
        self,
        vector: str,
        top_k: int,
    ) -> list[RagSearchMatch]:
        """Return assessment rows nearest to the query vector."""
        rows = self.session.exec(  # ty: ignore[no-matching-overload]
            text(_ASSESSMENT_SEARCH_SQL),
            params={
                "vector": vector,
                "top_k": top_k,
                "finalized_status": StatusType.FINALIZED.value,
            },
        ).all()
        return self._matches(rows, default_filename="generated-assessment")

    def search_knowledge(
        self,
        vector: str,
        top_k: int,
    ) -> list[RagSearchMatch]:
        """Return manual chunks nearest to the query vector."""
        rows = self.session.exec(  # ty: ignore[no-matching-overload]
            text(_KNOWLEDGE_SEARCH_SQL),
            params={
                "vector": vector,
                "top_k": top_k,
                "diet_manual": KnowledgeType.DIET_MANUAL.value,
                "nutrition_manual": KnowledgeType.NUTRITION_CARE_MANUAL.value,
            },
        ).all()
        return self._matches(rows)

    @staticmethod
    def _matches(
        rows: typing.Iterable[typing.Sequence[object]],
        default_filename: str | None = None,
    ) -> list[RagSearchMatch]:
        return [
            RagSearchMatch(
                document_id=int(typing.cast("int", row[0])),
                filename=str(
                    default_filename
                    if row[1] is None and default_filename is not None
                    else row[1],
                ),
                chunk_text=str(row[2]),
                similarity=float(str(row[3])),
            )
            for row in rows
        ]
