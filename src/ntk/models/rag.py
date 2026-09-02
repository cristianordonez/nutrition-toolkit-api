"""Models returned by retrieval-augmented generation endpoints."""

from __future__ import annotations

from pydantic import BaseModel


class RagSearchMatch(BaseModel):
    """One document chunk returned by vector similarity search."""

    document_id: int
    filename: str
    chunk_text: str
    similarity: float
