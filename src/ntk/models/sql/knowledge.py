# noqa: I002
"""SQL models for persisted clinical nutrition knowledge."""

from datetime import UTC, datetime

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import JSON, CheckConstraint, Column, Enum, UniqueConstraint
from sqlmodel import Field, Index, Relationship, SQLModel

from ntk.models.knowledge import KnowledgeType
from ntk.services.embedding_service import EMBEDDING_DIMENSIONS

KNOWLEDGE_EMBEDDING_DIMENSIONS = EMBEDDING_DIMENSIONS


class Knowledge(SQLModel, table=True):
    """A diet or nutrition care manual stored for retrieval."""

    __tablename__ = "knowledge"

    id: int | None = Field(default=None, primary_key=True)
    filename: str
    knowledge_type: KnowledgeType = Field(
        sa_column=Column(
            Enum(
                KnowledgeType,
                name="knowledge_type",
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
    chunks: list["KnowledgeChunk"] = Relationship(back_populates="knowledge")


class KnowledgeChunk(SQLModel, table=True):
    """A bounded text chunk extracted from a knowledge document."""

    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        UniqueConstraint("knowledge_id", "chunk_index"),
        CheckConstraint(
            "source_page_start IS NULL OR source_page_start >= 1",
            name="ck_knowledge_chunks_source_page_start",
        ),
        CheckConstraint(
            "source_page_end IS NULL OR source_page_start IS NULL "
            "OR source_page_end >= source_page_start",
            name="ck_knowledge_chunks_source_page_range",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    knowledge_id: int = Field(foreign_key="knowledge.id", index=True)
    chunk_index: int
    content: str
    section_title: str | None = None
    source_page_start: int | None = None
    source_page_end: int | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    knowledge: Knowledge = Relationship(back_populates="chunks")


class KnowledgeChunkEmbedding(SQLModel, table=True):
    """An embedding generated for one knowledge chunk."""

    __tablename__ = "knowledge_chunks_embeddings"
    __table_args__ = (
        Index(
            "ix_knowledge_chunks_embeddings_embedding_vector_hnsw",
            "embedding_vector",
            postgresql_using="hnsw",
            postgresql_ops={"embedding_vector": "vector_cosine_ops"},
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    knowledge_chunk_id: int = Field(foreign_key="knowledge_chunks.id", index=True)
    embedding_vector: list[float] = Field(
        sa_column=Column(
            VECTOR(KNOWLEDGE_EMBEDDING_DIMENSIONS).with_variant(JSON, "sqlite"),
            nullable=False,
        ),
    )
    model_name: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
