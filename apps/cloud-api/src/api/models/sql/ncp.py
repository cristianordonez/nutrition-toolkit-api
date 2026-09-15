"""SQL models for generated Nutrition Care Process (NCP) records.

These are keyed by an opaque ``person_identifier`` string supplied by the
desktop engine, not a foreign key to a local ``Person`` row -- cloud-api does
not persist Person/clinical data (see the split refactor plan).
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import JSON, Column, Enum, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlmodel import Field, Index, Relationship, SQLModel

from api.models.sql._constants import EMBEDDING_DIMENSIONS


class NutritionCareProcessStatus(StrEnum):
    """Lifecycle status for a generated Nutrition Care Process note."""

    DRAFT = "draft"
    FINALIZED = "finalized"
    DISCARDED = "discarded"


class NutritionClinicalNoteType(StrEnum):
    """Canonical nutrition note categories eligible for vector search."""

    NUTRITION_DIETARY = "Nutrition/Dietary"
    DIETICIAN = "Dietician"


class NutritionCareProcessSource(StrEnum):
    """Identify how a Nutrition Care Process note entered the system.

    Only ``GENERATED`` is produced by the current (post-split) generate flow.
    ``IMPORTED`` is kept for the deferred device-side NCP import/promotion
    feature (see the split refactor plan) -- that pipeline is not yet
    redesigned for the stateless cloud/device split, so nothing currently
    writes an ``IMPORTED`` row, but the column stays so that redesign doesn't
    also require a schema migration.
    """

    GENERATED = "generated"
    IMPORTED = "imported"


class NutritionCareProcess(SQLModel, table=True):
    """A Nutrition Care Process, keyed by an opaque person identifier."""

    __tablename__ = "nutrition_care_process"
    __table_args__ = (
        UniqueConstraint(
            "person_identifier",
            "content_hash",
            name="uq_ncp_person_content_hash",
        ),
    )
    id: int | None = Field(default=None, primary_key=True)
    person_identifier: str = Field(index=True)
    facility_identifier: str | None = Field(default=None, index=True)
    note_text: str
    content_hash: str = Field(index=True)
    created_by: str
    ncp_source: NutritionCareProcessSource = Field(
        default=NutritionCareProcessSource.GENERATED,
        sa_column=Column(
            Enum(
                NutritionCareProcessSource,
                name="nutrition_care_process_source",
                native_enum=False,
                create_constraint=True,
                values_callable=lambda enum_type: [item.value for item in enum_type],
            ),
            nullable=False,
            index=True,
        ),
    )
    source_filename: str | None = Field(default=None, index=True)
    status: NutritionCareProcessStatus = Field(
        default=NutritionCareProcessStatus.DRAFT,
        sa_column=Column(
            Enum(
                NutritionCareProcessStatus,
                name="nutrition_care_process_status",
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
    nutrition_embeddings: list[NutritionCareProcessEmbedding] = Relationship(
        sa_relationship=relationship(
            "NutritionCareProcessEmbedding",
            back_populates="nutrition_care_process",
            collection_class=list,
            cascade="all, delete-orphan",
        ),
    )


class NutritionCareProcessEmbedding(SQLModel, table=True):
    """An embedding for an eligible finalized Nutrition Care Process."""

    __tablename__ = "nutrition_care_process_embeddings"
    __table_args__ = (
        Index(
            "ix_nutrition_care_process_embeddings_vector_hnsw",
            "embedding_vector",
            postgresql_using="hnsw",
            postgresql_ops={"embedding_vector": "vector_cosine_ops"},
        ),
        Index(
            "uq_nutrition_care_process_embedding_ncp_id",
            "nutrition_care_process_id",
            unique=True,
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
    nutrition_care_process_id: int = Field(
        foreign_key="nutrition_care_process.id",
    )
    type: NutritionClinicalNoteType = Field(
        sa_column=Column(
            Enum(
                NutritionClinicalNoteType,
                name="nutrition_clinical_note_type",
                native_enum=False,
                create_constraint=True,
                values_callable=lambda enum_type: [item.value for item in enum_type],
            ),
            nullable=False,
            index=True,
        ),
    )
    model_name: str
    nutrition_care_process: NutritionCareProcess = Relationship(
        back_populates="nutrition_embeddings",
    )


__all__ = [
    "NutritionCareProcess",
    "NutritionCareProcessEmbedding",
    "NutritionCareProcessSource",
    "NutritionCareProcessStatus",
    "NutritionClinicalNoteType",
]
