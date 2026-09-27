"""Persisted units of clinical source material."""

from __future__ import annotations

import typing
from datetime import datetime  # noqa: TC003
from enum import StrEnum

from sqlalchemy import JSON, Column, Enum
from sqlalchemy.orm import relationship
from sqlmodel import Field, Relationship, SQLModel

from engine.models.clinical_facts import utc_now

if typing.TYPE_CHECKING:
    from .clinical_fact import ClinicalFact
    from .document import Document
    from .person import Person


class ClinicalSourceKind(StrEnum):
    PROGRESS_NOTE = "progress_note"
    REPORT_SECTION = "report_section"
    ORDER_ENTRY = "order_entry"
    LAB_SECTION = "lab_section"
    WOUND_ENTRY = "wound_entry"
    TEXT_BLOCK = "text_block"
    PASTED_TEXT = "pasted_text"
    API_RECORD = "api_record"
    MANUAL_ENTRY = "manual_entry"
    APPLICATION = "application"
    LEGACY = "legacy"


class SourceAuthority(StrEnum):
    """How strongly a source establishes a person's current clinical state."""

    AUTHORITATIVE_SNAPSHOT = "authoritative_snapshot"
    STRUCTURED_RECORD = "structured_record"
    CLINICAL_DOCUMENT = "clinical_document"
    HISTORICAL_DOCUMENT = "historical_document"
    UNKNOWN = "unknown"


class ExtractionStatus(StrEnum):
    PENDING = "pending"
    EXTRACTED = "extracted"
    SKIPPED = "skipped"
    FAILED = "failed"
    NOT_APPLICABLE = "not_applicable"


class ClinicalSource(SQLModel, table=True):
    """One logical source unit that may produce zero or more facts."""

    __tablename__ = "clinical_source"

    id: int | None = Field(default=None, primary_key=True)
    document_id: int | None = Field(
        default=None,
        foreign_key="document.id",
        index=True,
        ondelete="RESTRICT",
    )
    person_id: int | None = Field(
        default=None,
        foreign_key="person.id",
        index=True,
        ondelete="CASCADE",
    )
    source_kind: ClinicalSourceKind = Field(
        sa_column=Column(
            Enum(
                ClinicalSourceKind,
                name="clinical_source_kind",
                values_callable=lambda enum_type: [item.value for item in enum_type],
            ),
            nullable=False,
            index=True,
        ),
    )
    source_key: str = Field(max_length=64, index=True, unique=True)
    content: str | None = None
    raw_content: str | None = None
    content_hash: str | None = Field(default=None, max_length=64, index=True)
    title: str | None = None
    note_type: str | None = Field(default=None, index=True)
    author: str | None = None
    effective_at: datetime | None = Field(default=None, index=True)
    page_start: int | None = None
    page_end: int | None = None
    source_section: str | None = None
    locator: dict[str, typing.Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False),
    )
    source_system: str | None = Field(default=None, index=True)
    source_record_type: str | None = Field(default=None, index=True)
    source_record_id: str | None = Field(default=None, index=True)
    source_record_version: str | None = None
    source_document_id: str | None = Field(default=None, index=True)
    source_endpoint: str | None = None
    source_authority: SourceAuthority = Field(
        default=SourceAuthority.UNKNOWN,
        sa_column=Column(
            Enum(
                SourceAuthority,
                name="source_authority",
                values_callable=lambda enum_type: [item.value for item in enum_type],
            ),
            nullable=False,
            default=SourceAuthority.UNKNOWN.value,
            index=True,
        ),
    )
    extraction_status: ExtractionStatus = Field(
        default=ExtractionStatus.PENDING,
        sa_column=Column(
            Enum(
                ExtractionStatus,
                name="extraction_status",
                values_callable=lambda enum_type: [item.value for item in enum_type],
            ),
            nullable=False,
            default=ExtractionStatus.PENDING.value,
            index=True,
        ),
    )
    source_metadata: dict[str, typing.Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False),
    )
    received_at: datetime = Field(default_factory=utc_now, index=True)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    document: Document = Relationship(back_populates="sources")
    person: Person = Relationship(back_populates="clinical_sources")
    facts: list[ClinicalFact] = Relationship(
        sa_relationship=relationship(
            "ClinicalFact",
            back_populates="source",
            collection_class=list,
        ),
    )

    @property
    def note_date(self) -> datetime | None:
        """Compatibility name used by note/context consumers."""
        return self.effective_at

    @property
    def note_text(self) -> str | None:
        """Compatibility name used by note/context consumers."""
        return self.content

    @property
    def raw_text(self) -> str | None:
        """Compatibility name used by note/context consumers."""
        return self.raw_content

    @property
    def note_key(self) -> str:
        """Compatibility name for the stable source key."""
        return self.source_key


__all__ = [
    "ClinicalSource",
    "ClinicalSourceKind",
    "ExtractionStatus",
    "SourceAuthority",
]
