"""Models returned by retrieval-augmented generation endpoints."""

from __future__ import annotations

from uuid import UUID  # noqa: TC003

from pydantic import BaseModel


class RagSearchMatch(BaseModel):
    """One document chunk returned by vector similarity search."""

    document_id: UUID
    filename: str
    chunk_text: str
    similarity: float
