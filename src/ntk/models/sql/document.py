"""Persisted source document metadata."""

from __future__ import annotations

import typing
from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import relationship
from sqlmodel import Field, Relationship, SQLModel

if typing.TYPE_CHECKING:
    from .extracted_fact import ExtractedFact


class Document(SQLModel, table=True):
    """A file imported for extraction or retrieval."""

    __tablename__ = "document"

    id: int | None = Field(default=None, primary_key=True)
    filename: str
    file_type: str = Field(index=True)
    checksum: str = Field(index=True, unique=True)
    storage_uri: str
    imported_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    document_type: str = Field(index=True)
    sources: list[DocumentSource] = Relationship(
        sa_relationship=relationship(
            "DocumentSource",
            back_populates="document",
            collection_class=list,
        ),
    )


class DocumentSourceType(StrEnum):
    PDF = "pdf"
    CSV = "csv"
    TEXT = "text"
    API = "api"


class DocumentSource(SQLModel, table=True):
    """A page, section, or API payload within an imported document."""

    __tablename__ = "document_source"
    __table_args__ = (UniqueConstraint("document_id", "source_page", "evidence_hash"),)

    id: int | None = Field(default=None, primary_key=True)
    document_id: int = Field(foreign_key="document.id", index=True)
    source_type: DocumentSourceType = Field(index=True)
    source_page: int | None = None
    evidence_hash: str = Field(max_length=64, index=True)
    source_section: str | None = None
    document: Document = Relationship(back_populates="sources")
    extracted_facts: list[ExtractedFact] = Relationship(
        sa_relationship=relationship(
            "ExtractedFact",
            back_populates="source",
            collection_class=list,
        ),
    )
