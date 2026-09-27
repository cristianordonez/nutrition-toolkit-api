"""Imported clinical source artifact metadata."""

from __future__ import annotations

import typing
from datetime import datetime  # noqa: TC003

from sqlalchemy import JSON, Column, Index, text
from sqlalchemy.orm import relationship
from sqlmodel import Field, Relationship, SQLModel

from engine.models.clinical_facts import utc_now

if typing.TYPE_CHECKING:
    from .clinical_source import ClinicalSource
    from .facility import Facility


class Document(SQLModel, table=True):
    """An imported file artifact, separate from its logical clinical sources."""

    __tablename__ = "document"
    __table_args__ = (
        Index(
            "uq_document_unscoped_checksum",
            "checksum",
            unique=True,
            sqlite_where=text("facility_id IS NULL"),
        ),
        Index(
            "uq_document_facility_checksum",
            "facility_id",
            "checksum",
            unique=True,
            sqlite_where=text("facility_id IS NOT NULL"),
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    facility_id: int | None = Field(
        default=None,
        foreign_key="facility.id",
        index=True,
        ondelete="RESTRICT",
    )
    filename: str
    media_type: str = Field(index=True)
    checksum: str = Field(index=True)
    storage_uri: str | None = None
    byte_size: int | None = Field(default=None, ge=0)
    source_observed_at: datetime | None = Field(default=None, index=True)
    document_type: str = Field(index=True)
    document_metadata: dict[str, typing.Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False),
    )
    imported_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    facility: Facility = Relationship(back_populates="documents")
    sources: list[ClinicalSource] = Relationship(
        sa_relationship=relationship(
            "ClinicalSource",
            back_populates="document",
            collection_class=list,
        ),
    )


__all__ = ["Document"]
