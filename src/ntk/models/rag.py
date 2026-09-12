"""Models returned by retrieval-augmented generation endpoints."""

from __future__ import annotations

from pydantic import BaseModel

from ntk.models.knowledge import KnowledgeType  # noqa: TC001 - required by Pydantic


class RagSearchMatch(BaseModel):
    """One document chunk returned by vector similarity search."""

    document_id: int
    filename: str
    chunk_text: str
    similarity: float
    knowledge_type: KnowledgeType | None = None
    section_title: str | None = None
    source_page_start: int | None = None
    source_page_end: int | None = None
