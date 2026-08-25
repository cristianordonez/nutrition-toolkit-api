"""SQL models for persisted nutrition assessments."""

from __future__ import annotations

from datetime import UTC, date, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import JSON, Column, Enum
from sqlmodel import Field, Index, SQLModel

ASSESSMENT_EMBEDDING_DIMENSIONS = 1536


class AssessmentSource(StrEnum):
    """Identify source for nutrition assessments."""

    UPLOADED = "uploaded"
    GENERATED = "generated"


class Assessment(SQLModel, table=True):
    """One searchable nutrition assessment extracted from a source document."""

    __tablename__ = "assessment"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    content: str
    source: AssessmentSource = Field(
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
    source_filename: str | None
    content_hash: str = Field(unique=True, index=True)
    assessment_index: int
    assessment_date: date | None = Field(default=None, index=True)
    created_by: str = Field(index=True)

    def to_console(self) -> str:
        """Render the assessment content."""
        return self.content


class AssessmentEmbedding(SQLModel, table=True):
    """An embedding generated for one complete nutrition assessment."""

    __tablename__ = "assessment_embeddings"
    __table_args__ = (
        Index(
            "ix_assessment_embeddings_embedding_vector_hnsw",
            "embedding_vector",
            postgresql_using="hnsw",
            postgresql_ops={"embedding_vector": "vector_cosine_ops"},
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    embedding_vector: list[float] = Field(
        sa_column=Column(
            VECTOR(ASSESSMENT_EMBEDDING_DIMENSIONS).with_variant(JSON, "sqlite"),
            nullable=False,
        ),
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    assessment_id: UUID = Field(foreign_key="assessment.id", index=True)
    model_name: str
