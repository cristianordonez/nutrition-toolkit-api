"""What a manual search returns to its caller and to the agent."""

from __future__ import annotations

from pydantic import BaseModel

from engine.models.sql.knowledge import KnowledgeType  # noqa: TC001


class RagSearchMatch(BaseModel):
    """One passage of a manual returned by similarity search."""

    document_id: int
    filename: str
    chunk_text: str
    similarity: float
    knowledge_type: KnowledgeType | None = None
    section_title: str | None = None
    source_page_start: int | None = None
    source_page_end: int | None = None


__all__ = ["RagSearchMatch"]
