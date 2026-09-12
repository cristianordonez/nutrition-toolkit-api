"""Vector-search persistence operations."""

from __future__ import annotations

import typing

from sqlalchemy import text

from ntk.models.knowledge import KnowledgeType
from ntk.models.rag import RagSearchMatch
from ntk.models.sql.person import StatusType

if typing.TYPE_CHECKING:
    from sqlmodel import Session

_ASSESSMENT_SEARCH_SQL = """
    SELECT a.id, a.source_filename, a.content,
           1 - (e.embedding_vector <=> CAST(:vector AS vector)) AS similarity
    FROM person_assessment_embeddings e
    JOIN person_assessment a ON a.id = e.person_assessment_id
    WHERE a.status = :finalized_status
    ORDER BY e.embedding_vector <=> CAST(:vector AS vector)
    LIMIT :top_k
"""

_KNOWLEDGE_SEARCH_SQL = """
    SELECT k.id, k.filename, c.content,
           1 - (e.embedding_vector <=> CAST(:vector AS vector)) AS similarity,
           k.knowledge_type, c.section_title,
           c.source_page_start, c.source_page_end
    FROM knowledge_chunks_embeddings e
    JOIN knowledge_chunks c ON c.id = e.knowledge_chunk_id
    JOIN knowledge k ON k.id = c.knowledge_id
    WHERE (
        (:include_diet_manual AND k.knowledge_type = :diet_manual)
        OR (
            :include_nutrition_care_manual
            AND k.knowledge_type = :nutrition_care_manual
        )
    )
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
        *,
        document_type: KnowledgeType | None = None,
    ) -> list[RagSearchMatch]:
        """Return matching chunks from either or both supported manuals."""
        rows = self.session.exec(  # ty: ignore[no-matching-overload]
            text(_KNOWLEDGE_SEARCH_SQL),
            params={
                "vector": vector,
                "top_k": top_k,
                "include_diet_manual": document_type
                in {None, KnowledgeType.DIET_MANUAL},
                "include_nutrition_care_manual": document_type
                in {None, KnowledgeType.NUTRITION_CARE_MANUAL},
                "diet_manual": KnowledgeType.DIET_MANUAL.value,
                "nutrition_care_manual": KnowledgeType.NUTRITION_CARE_MANUAL.value,
            },
        ).all()
        return self._knowledge_matches(rows)

    @staticmethod
    def _knowledge_matches(
        rows: typing.Iterable[typing.Sequence[object]],
    ) -> list[RagSearchMatch]:
        """Build knowledge matches with source, section, and page provenance."""
        return [
            RagSearchMatch(
                document_id=int(typing.cast("int", row[0])),
                filename=str(row[1]),
                chunk_text=str(row[2]),
                similarity=float(str(row[3])),
                knowledge_type=KnowledgeType(str(row[4])),
                section_title=None if row[5] is None else str(row[5]),
                source_page_start=None if row[6] is None else int(str(row[6])),
                source_page_end=None if row[7] is None else int(str(row[7])),
            )
            for row in rows
        ]

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
