"""Resident identity, facility-stay, progress-note, and assessment models."""

from __future__ import annotations

import typing
from datetime import UTC, date, datetime
from enum import StrEnum

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import JSON, Column, Enum, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlmodel import Field, Index, Relationship, SQLModel

from ntk.models.sql.clinical import (
    ClinicalFactType,
    ResidentClinicalFact,
    ResidentEdema,
    ResidentLab,
    ResidentMealIntake,
    ResidentOrder,
    ResidentWeight,
    ResidentWound,
)
from ntk.services.embedding_service import EMBEDDING_DIMENSIONS

if typing.TYPE_CHECKING:
    from ntk.models.sql import Facility

    from .extracted_fact import ExtractedFact


class StatusType(StrEnum):
    """Status for resident assessments."""

    DRAFT = "draft"
    FINALIZED = "finalized"
    DISCARDED = "discarded"


class AssessmentSource(StrEnum):
    """Identify how a resident assessment entered the system."""

    GENERATED = "generated"
    IMPORTED = "imported"


class ExtractionStatus(StrEnum):
    PENDING = "pending"
    EXTRACTED = "extracted"
    SKIPPED = "skipped"
    FAILED = "failed"


class ResidentFacilityStay(SQLModel, table=True):
    """Map resident to data from different facilities."""

    __tablename__ = "resident_facility_stay"
    __table_args__ = (UniqueConstraint("facility_id", "resident_id", "admitted_at"),)
    id: int | None = Field(default=None, primary_key=True)
    resident_id: int = Field(foreign_key="resident.id")
    facility_id: int = Field(foreign_key="facility.id")
    facility_resident_identifier: str | None = Field(default=None, index=True)
    admitted_at: datetime | None = None
    discharged_at: datetime | None = None
    # relationships
    resident: Resident = Relationship(
        sa_relationship=relationship("Resident", back_populates="facility_stays"),
    )
    facility: Facility = Relationship(
        sa_relationship=relationship("Facility", back_populates="resident_stays"),
    )


class ResidentIdentifier(SQLModel, table=True):
    """Uniquely map a facility-scoped external identifier to one resident."""

    __tablename__ = "resident_identifier"
    __table_args__ = (UniqueConstraint("facility_id", "facility_resident_identifier"),)
    id: int | None = Field(default=None, primary_key=True)
    resident_id: int = Field(foreign_key="resident.id", index=True)
    facility_id: int = Field(foreign_key="facility.id", index=True)
    facility_resident_identifier: str = Field(index=True)


class Resident(SQLModel, table=True):
    __tablename__ = "resident"
    id: int | None = Field(default=None, primary_key=True)
    name: str
    date_of_birth: date | None = None
    sex: str | None = None
    height_in: float | None = Field(default=None, gt=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    facility_stays: list[ResidentFacilityStay] = Relationship(
        sa_relationship=relationship("ResidentFacilityStay", back_populates="resident"),
    )
    weights: list[ResidentWeight] = Relationship(
        sa_relationship=relationship("ResidentWeight", back_populates="resident"),
    )
    orders: list[ResidentOrder] = Relationship(
        sa_relationship=relationship("ResidentOrder", back_populates="resident"),
    )
    labs: list[ResidentLab] = Relationship(
        sa_relationship=relationship("ResidentLab", back_populates="resident"),
    )
    edema: list[ResidentEdema] = Relationship(
        sa_relationship=relationship(
            "ResidentEdema",
            back_populates="resident",
            collection_class=list,
        ),
    )
    meal_intakes: list[ResidentMealIntake] = Relationship(
        sa_relationship=relationship(
            "ResidentMealIntake",
            back_populates="resident",
            collection_class=list,
        ),
    )
    clinical_facts: list[ResidentClinicalFact] = Relationship(
        sa_relationship=relationship(
            "ResidentClinicalFact",
            back_populates="resident",
            collection_class=list,
        ),
    )
    progress_notes: list[ResidentProgressNote] = Relationship(
        sa_relationship=relationship(
            "ResidentProgressNote",
            back_populates="resident",
        ),
    )
    wounds: list[ResidentWound] = Relationship(
        sa_relationship=relationship("ResidentWound", back_populates="resident"),
    )
    assessments: list[ResidentAssessment] = Relationship(
        sa_relationship=relationship(
            "ResidentAssessment",
            back_populates="resident",
            passive_deletes="all",
        ),
    )
    extracted_facts: list[ExtractedFact] = Relationship(
        sa_relationship=relationship(
            "ExtractedFact",
            back_populates="resident",
            collection_class=list,
        ),
    )


class ResidentProgressNote(SQLModel, table=True):
    """A persisted resident progress note."""

    __tablename__ = "resident_progress_note"
    __table_args__ = (
        UniqueConstraint(
            "resident_id",
            "note_key",
        ),
    )
    id: int | None = Field(default=None, primary_key=True)
    resident_id: int = Field(foreign_key="resident.id", index=True)
    resident_facility_stay_id: int | None = Field(
        default=None,
        foreign_key="resident_facility_stay.id",
    )
    note_date: datetime = Field(index=True)
    note_type: str | None = None
    author: str | None = None
    note_text: str
    raw_text: str
    note_key: str = Field(index=True, unique=True)
    extraction_status: ExtractionStatus = Field(
        sa_column=Column(
            Enum(
                ExtractionStatus,
                name="extraction_status",
                values_callable=lambda enum_type: [item.value for item in enum_type],
            ),
            nullable=False,
            default="pending",
            index=True,
        ),
    )
    resident: Resident = Relationship(back_populates="progress_notes")
    source_id: int | None = Field(
        default=None,
        foreign_key="document_source.id",
        index=True,
    )


class ResidentAssessment(SQLModel, table=True):
    """A generated or imported nutrition assessment for one resident."""

    __tablename__ = "resident_assessment"
    __table_args__ = (UniqueConstraint("resident_id", "content_hash"),)
    id: int | None = Field(default=None, primary_key=True)
    resident_id: int = Field(
        foreign_key="resident.id",
        index=True,
    )
    resident_facility_stay_id: int | None = Field(
        default=None,
        foreign_key="resident_facility_stay.id",
    )
    source_progress_note_id: int | None = Field(
        default=None,
        foreign_key="resident_progress_note.id",
        index=True,
        unique=True,
    )
    content: str
    assessment_source: AssessmentSource = Field(
        default=AssessmentSource.GENERATED,
        sa_column=Column(
            Enum(
                AssessmentSource,
                name="assessment_source",
                native_enum=False,
                create_constraint=True,
                values_callable=lambda enum_type: [item.value for item in enum_type],
            ),
            nullable=False,
            index=True,
        ),
    )
    source_filename: str | None = None
    content_hash: str = Field(index=True)
    assessment_index: int = 0
    assessment_date: date = Field(index=True)
    created_by: str = Field(index=True)
    status: StatusType = Field(
        default=StatusType.DRAFT,
        sa_column=Column(
            Enum(
                StatusType,
                name="status_type",
                values_callable=lambda enum_type: [item.value for item in enum_type],
            ),
            nullable=False,
            index=True,
        ),
    )
    model_name: str | None = None
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        index=True,
    )
    finalized_at: datetime | None = None
    resident: Resident = Relationship(
        back_populates="assessments",
    )
    embeddings: list[ResidentAssessmentEmbedding] = Relationship(
        sa_relationship=relationship(
            "ResidentAssessmentEmbedding",
            back_populates="resident_assessment",
            collection_class=list,
        ),
    )


class ResidentAssessmentEmbedding(SQLModel, table=True):
    """An embedding generated for one complete nutrition assessment."""

    __tablename__ = "resident_assessment_embeddings"
    __table_args__ = (
        Index(
            "ix_resident_assessment_embeddings_embedding_vector_hnsw",
            "embedding_vector",
            postgresql_using="hnsw",
            postgresql_ops={"embedding_vector": "vector_cosine_ops"},
        ),
    )
    id: int | None = Field(default=None, primary_key=True)
    embedding_vector: list[float] = Field(
        sa_column=Column(
            VECTOR(EMBEDDING_DIMENSIONS).with_variant(
                JSON,
                "sqlite",
            ),
            nullable=False,
        ),
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    resident_assessment_id: int = Field(
        foreign_key="resident_assessment.id",
        index=True,
        unique=True,
    )
    model_name: str
    resident_assessment: ResidentAssessment = Relationship(
        sa_relationship=relationship(
            "ResidentAssessment",
            back_populates="embeddings",
        ),
    )


__all__ = [
    "AssessmentSource",
    "ClinicalFactType",
    "ExtractionStatus",
    "Resident",
    "ResidentAssessment",
    "ResidentAssessmentEmbedding",
    "ResidentClinicalFact",
    "ResidentEdema",
    "ResidentFacilityStay",
    "ResidentIdentifier",
    "ResidentLab",
    "ResidentMealIntake",
    "ResidentOrder",
    "ResidentProgressNote",
    "ResidentWeight",
    "ResidentWound",
    "StatusType",
]
