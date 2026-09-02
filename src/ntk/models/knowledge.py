"""Pydantic types for clinical nutrition knowledge workflows."""

from __future__ import annotations

import typing
from datetime import datetime  # noqa: TC003
from enum import StrEnum

from pydantic import BaseModel, computed_field

from ntk.utils.misc import require_id

if typing.TYPE_CHECKING:
    from collections.abc import Sequence

    from ntk.models.sql.knowledge import Knowledge


class KnowledgeType(StrEnum):
    """Identify the supported clinical knowledge sources."""

    DIET_MANUAL = "diet-manual"
    NUTRITION_CARE_MANUAL = "nutrition-care-manual"


class KnowledgeChunkPublic(BaseModel):
    """Knowledge chunk returned by the API."""

    id: int
    knowledge_id: int
    chunk_index: int
    content: str
    created_at: datetime


class KnowledgePublic(BaseModel):
    """Knowledge document and its persisted chunks returned by the API."""

    id: int
    filename: str
    knowledge_type: KnowledgeType
    file_hash: str
    synced_at: datetime
    chunks: list[KnowledgeChunkPublic]


class KnowledgeIngestResponsePublic(BaseModel):
    """Public response for knowledge ingestion."""

    documents: list[KnowledgePublic]

    @computed_field
    @property
    def chunk_count(self) -> int:
        """Return the total number of chunks across all documents."""
        return sum(len(document.chunks) for document in self.documents)

    @classmethod
    def from_documents(
        cls,
        documents: Sequence[Knowledge],
    ) -> KnowledgeIngestResponsePublic:
        """Build a public response from persisted knowledge documents."""
        return cls(
            documents=[
                KnowledgePublic(
                    id=require_id(knowledge.id),
                    filename=knowledge.filename,
                    knowledge_type=knowledge.knowledge_type,
                    file_hash=knowledge.file_hash,
                    synced_at=knowledge.synced_at,
                    chunks=[
                        KnowledgeChunkPublic(
                            id=require_id(chunk.id),
                            knowledge_id=chunk.knowledge_id,
                            chunk_index=chunk.chunk_index,
                            content=chunk.content,
                            created_at=chunk.created_at,
                        )
                        for chunk in knowledge.chunks
                    ],
                )
                for knowledge in documents
            ],
        )
