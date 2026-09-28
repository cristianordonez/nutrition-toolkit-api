"""Non-table schemas for manual ingestion and its results.

The persisted shapes are in ``models/sql/knowledge.py``. These are the shapes
either side of them: what an extractor produces, what the chunker hands the
repository before any of it has an id, and what a caller is given back once
the session that loaded it is gone.
"""

from __future__ import annotations

import typing
from datetime import datetime  # noqa: TC003
from enum import StrEnum

from pydantic import BaseModel, Field, computed_field, model_validator

from engine.models.sql.knowledge import KnowledgeType  # noqa: TC001
from engine.utils.misc import require_id

if typing.TYPE_CHECKING:
    from collections.abc import Sequence

    from engine.models.sql.knowledge import Knowledge


class KnowledgeSectionType(StrEnum):
    """What a passage of a manual is, before it is considered for indexing.

    Only ``CONTENT`` is worth embedding. A reference list or a table of
    contents matches a query on wording alone and would crowd out the guidance
    the wording was asking about.
    """

    CONTENT = "content"
    REFERENCES = "references"
    TABLE_OF_CONTENTS = "table_of_contents"
    METADATA = "metadata"


class ExtractedKnowledgePage(BaseModel):
    """Readable text retained with its one-based source page."""

    page_number: int = Field(ge=1)
    text: str
    section_path: tuple[str, ...] = ()
    """Article hierarchy from the PDF outline, including continuation pages."""


class KnowledgeChunkCreate(BaseModel):
    """One substantive passage of a manual, with its page provenance.

    Pages are required and ordered because a retrieved passage has to be
    checkable against the printed manual. A citation a dietitian cannot turn
    back to is not usable clinical guidance.
    """

    content: str = Field(min_length=1)
    section_title: str | None = None
    source_page_start: int = Field(ge=1)
    source_page_end: int = Field(ge=1)
    section_path: str | None = None

    @model_validator(mode="after")
    def validate_page_range(self) -> KnowledgeChunkCreate:
        """Require a page range ordered from first source page to last."""
        if self.source_page_end < self.source_page_start:
            msg = "source_page_end must not precede source_page_start"
            raise ValueError(msg)
        return self


class KnowledgeChunkPublic(BaseModel):
    """One stored chunk, detached from the session that loaded it."""

    id: int
    knowledge_id: int
    chunk_index: int
    content: str
    section_title: str | None
    source_page_start: int | None
    source_page_end: int | None
    created_at: datetime


class KnowledgePublic(BaseModel):
    """One stored manual and its chunks, detached from their session."""

    id: int
    filename: str
    knowledge_type: KnowledgeType
    file_hash: str
    synced_at: datetime
    chunks: list[KnowledgeChunkPublic]


class KnowledgeIngestResponsePublic(BaseModel):
    """What an ingest run reports once its database session has closed.

    The SQLModel rows cannot be returned directly: ``chunks`` loads lazily, so
    serializing one after the controller's session closes raises rather than
    rendering. Reading every value here is what detaches them.
    """

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
        """Build a detached response from persisted manuals."""
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


__all__ = [
    "ExtractedKnowledgePage",
    "KnowledgeChunkCreate",
    "KnowledgeChunkPublic",
    "KnowledgeIngestResponsePublic",
    "KnowledgePublic",
    "KnowledgeSectionType",
]
