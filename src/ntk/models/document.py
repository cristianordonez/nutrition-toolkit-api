# noqa: I002
"""Database models for ingested source documents and their RAG data."""

from datetime import UTC, date, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import JSON, Column, Enum, UniqueConstraint
from sqlmodel import Field, Index, Relationship, SQLModel

EMBEDDING_DIMENSIONS = 1536


class DocumentType(StrEnum):
    """Identify every document type accepted by the application."""

    PCC_PROGRESS_REPORT = "pcc-progress-report"
    ASSESSMENT = "assessment"
    DIET_MANUAL = "diet-manual"
    NUTRITION_CARE_MANUAL = "nutrition-care-manual"
    PCC_WEIGHT_HISTORY_REPORT = "pcc-weight-history-report"
    PCC_ORDER_LIST_REPORT = "pcc-order-list-report"
    PCC_WEIGHT_VITALS_SUMMARY = "pcc-weight-vitals-summary"


class StoredDocumentType(StrEnum):
    """Identify document types that may be persisted for retrieval."""

    PCC_PROGRESS_REPORT = "pcc-progress-report"
    ASSESSMENT = "assessment"
    DIET_MANUAL = "diet-manual"
    NUTRITION_CARE_MANUAL = "nutrition-care-manual"


class ChunkType(StrEnum):
    """Classify the content stored in a document chunk."""

    DIET_MANUAL = "diet-manual"
    NUTRITION_CARE_MANUAL = "nutrition-care-manual"
    ASSESSMENT = "assessment"


class Document(SQLModel, table=True):
    """A source document available to the RAG system."""

    __tablename__ = "document"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    filename: str
    document_type: StoredDocumentType = Field(
        sa_column=Column(
            Enum(
                StoredDocumentType,
                name="document_type",
                native_enum=False,
                create_constraint=True,
                values_callable=lambda enum_type: [item.value for item in enum_type],
            ),
            nullable=False,
            index=True,
        ),
    )
    file_hash: str = Field(index=True)
    synced_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    chunks: list["DocumentChunk"] = Relationship(back_populates="document")


class DocumentChunk(SQLModel, table=True):
    """A sequential text chunk extracted from an ingested document."""

    __tablename__ = "document_chunks"
    __table_args__ = (UniqueConstraint("document_id", "chunk_index"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    document_id: UUID = Field(foreign_key="document.id", index=True)
    chunk_index: int
    chunk_type: ChunkType = Field(
        sa_column=Column(
            Enum(
                ChunkType,
                name="chunk_type",
                native_enum=False,
                create_constraint=True,
                values_callable=lambda enum_type: [item.value for item in enum_type],
            ),
            nullable=False,
            index=True,
        ),
    )
    content: str
    content_hash: str | None = Field(default=None, unique=True, index=True)
    assessment_date: date | None = Field(default=None, index=True)
    chunk_metadata: dict[str, object] = Field(
        default_factory=dict,
        alias="metadata",
        sa_column=Column("metadata", JSON, nullable=False),
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    document: Document = Relationship(back_populates="chunks")
    embeddings: list["DocumentEmbedding"] = Relationship(back_populates="chunk")


class DocumentEmbedding(SQLModel, table=True):
    """An embedding vector generated for a document chunk."""

    __tablename__ = "document_embeddings"
    __table_args__ = (
        Index(
            "ix_document_embeddings_embedding_vector_hnsw",
            "embedding_vector",
            postgresql_using="hnsw",
            postgresql_ops={"embedding_vector": "vector_cosine_ops"},
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    document_chunk_id: UUID = Field(foreign_key="document_chunks.id", index=True)
    embedding_vector: list[float] = Field(
        sa_column=Column(
            VECTOR(EMBEDDING_DIMENSIONS).with_variant(JSON, "sqlite"),
            nullable=False,
        ),
    )
    model_name: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    chunk: DocumentChunk = Relationship(back_populates="embeddings")
