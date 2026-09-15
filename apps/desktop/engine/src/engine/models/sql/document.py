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
    from .facility import Facility


class Document(SQLModel, table=True):
    """A file imported for extraction or retrieval."""

    __tablename__ = "document"

    id: int | None = Field(default=None, primary_key=True)
    filename: str
    file_type: str = Field(index=True)
    checksum: str = Field(index=True, unique=True)
    storage_uri: str
    imported_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source_observed_at: datetime | None = Field(default=None, index=True)
    document_type: str = Field(index=True)
    facility_id: int | None = Field(
        default=None,
        foreign_key="facility.id",
        index=True,
    )
    facility: Facility | None = Relationship(
        sa_relationship=relationship("Facility", back_populates="documents"),
    )
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


class SourceAuthority(StrEnum):
    """How strongly a source establishes a person's current clinical state."""

    AUTHORITATIVE_SNAPSHOT = "authoritative_snapshot"
    STRUCTURED_RECORD = "structured_record"
    CLINICAL_DOCUMENT = "clinical_document"
    HISTORICAL_DOCUMENT = "historical_document"
    UNKNOWN = "unknown"


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
    source_system: str | None = Field(default=None, index=True)
    source_record_type: str | None = Field(default=None, index=True)
    source_record_id: str | None = Field(default=None, index=True)
    source_record_version: str | None = None
    source_document_id: str | None = Field(default=None, index=True)
    source_endpoint: str | None = None
    source_authority: SourceAuthority = Field(
        default=SourceAuthority.UNKNOWN,
        index=True,
    )
    received_at: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)
    document: Document = Relationship(back_populates="sources")
    extracted_facts: list[ExtractedFact] = Relationship(
        sa_relationship=relationship(
            "ExtractedFact",
            back_populates="source",
            collection_class=list,
        ),
    )


__all__ = [
    "Document",
    "DocumentSource",
    "DocumentSourceType",
    "SourceAuthority",
]
