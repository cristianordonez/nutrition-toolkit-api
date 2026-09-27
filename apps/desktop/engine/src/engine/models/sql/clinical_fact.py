"""Generic persisted resident clinical facts."""

from __future__ import annotations

import typing
from datetime import datetime  # noqa: TC003
from enum import StrEnum

from sqlalchemy import JSON, CheckConstraint, Column, Index, UniqueConstraint, text
from sqlmodel import Field, Relationship, SQLModel

from engine.models.clinical_facts import utc_now

if typing.TYPE_CHECKING:
    from .clinical_source import ClinicalSource
    from .person import Person


class ExtractionMethod(StrEnum):
    DETERMINISTIC = "deterministic"
    AI = "ai"
    API = "api"
    IMPORT = "import"
    MANUAL = "manual"
    CALCULATED = "calculated"
    APPLICATION = "application"


class ClinicalFact(SQLModel, table=True):
    """A validated typed payload in a queryable persistence envelope."""

    __tablename__ = "clinical_fact"
    __table_args__ = (
        UniqueConstraint(
            "clinical_source_id",
            "fact_type",
            "identity_hash",
            name="uq_clinical_fact_source_identity",
        ),
        Index(
            "uq_clinical_fact_without_source_identity",
            "person_id",
            "fact_type",
            "identity_hash",
            unique=True,
            sqlite_where=text("clinical_source_id IS NULL"),
        ),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_clinical_fact_confidence",
        ),
        CheckConstraint(
            "payload_schema_version > 0",
            name="ck_clinical_fact_payload_version",
        ),
        Index(
            "ix_clinical_fact_person_type_effective",
            "person_id",
            "fact_type",
            "effective_at",
            "id",
        ),
        Index(
            "ix_clinical_fact_person_type_status_effective",
            "person_id",
            "fact_type",
            "lifecycle_status",
            "effective_at",
        ),
        Index(
            "ix_clinical_fact_person_type_concept_effective",
            "person_id",
            "fact_type",
            "concept_key",
            "effective_at",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    person_id: int = Field(
        foreign_key="person.id",
        index=True,
        ondelete="CASCADE",
    )
    clinical_source_id: int | None = Field(
        default=None,
        foreign_key="clinical_source.id",
        index=True,
        nullable=True,
        ondelete="CASCADE",
    )
    fact_type: str = Field(index=True)
    payload: dict[str, typing.Any] = Field(sa_column=Column(JSON, nullable=False))
    payload_schema_version: int = Field(default=1)
    effective_at: datetime | None = Field(default=None, index=True)
    observed_at: datetime | None = Field(default=None, index=True)
    ended_at: datetime | None = Field(default=None, index=True)
    lifecycle_status: str | None = Field(default=None, index=True)
    concept_key: str | None = Field(default=None, index=True)
    identity_hash: str = Field(max_length=64, index=True)
    content_hash: str = Field(max_length=64, index=True)
    extraction_method: ExtractionMethod = Field(
        default=ExtractionMethod.DETERMINISTIC,
        index=True,
    )
    confidence: float | None = None
    confidence_reason: str | None = None
    model_name: str | None = None
    extractor_name: str | None = None
    extractor_version: str | None = None
    created_at: datetime = Field(default_factory=utc_now, index=True)
    updated_at: datetime = Field(default_factory=utc_now)

    person: Person = Relationship(back_populates="clinical_facts")
    source: ClinicalSource = Relationship(back_populates="facts")


__all__ = ["ClinicalFact", "ExtractionMethod"]
