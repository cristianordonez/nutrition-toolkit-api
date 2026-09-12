"""Pydantic types for clinical nutrition knowledge workflows."""

from __future__ import annotations

import typing
from datetime import datetime  # noqa: TC003
from enum import StrEnum

from pydantic import BaseModel, Field, computed_field, model_validator

from ntk.utils.misc import require_id

if typing.TYPE_CHECKING:
    from collections.abc import Sequence

    from ntk.models.sql.knowledge import Knowledge


class KnowledgeType(StrEnum):
    """Identify the supported clinical knowledge sources."""

    DIET_MANUAL = "diet-manual"
    NUTRITION_CARE_MANUAL = "nutrition-care-manual"


class KnowledgeSectionType(StrEnum):
    """Classify extracted manual sections before semantic indexing."""

    CONTENT = "content"
    REFERENCES = "references"
    TABLE_OF_CONTENTS = "table_of_contents"
    METADATA = "metadata"


class ExtractedKnowledgePage(BaseModel):
    """Readable text retained with its one-based source page."""

    page_number: int = Field(ge=1)
    text: str


class KnowledgeChunkCreate(BaseModel):
    """One substantive knowledge chunk with deterministic provenance."""

    content: str = Field(min_length=1)
    section_title: str | None = None
    source_page_start: int = Field(ge=1)
    source_page_end: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_page_range(self) -> KnowledgeChunkCreate:
        """Require a page range ordered from first source page to last."""
        if self.source_page_end < self.source_page_start:
            msg = "source_page_end must be on or after source_page_start"
            raise ValueError(msg)
        return self


class KnowledgeChunkPublic(BaseModel):
    """Knowledge chunk returned by the API."""

    id: int
    knowledge_id: int
    chunk_index: int
    content: str
    section_title: str | None
    source_page_start: int | None
    source_page_end: int | None
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
                            section_title=chunk.section_title,
                            source_page_start=chunk.source_page_start,
                            source_page_end=chunk.source_page_end,
                            created_at=chunk.created_at,
                        )
                        for chunk in knowledge.chunks
                    ],
                )
                for knowledge in documents
            ],
        )
