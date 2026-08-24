# noqa: I002
"""SQL models for persisted clinical nutrition knowledge."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import JSON, Column, Enum, UniqueConstraint
from sqlmodel import Field, Index, Relationship, SQLModel

from ntk.models.knowledge import KnowledgeType

KNOWLEDGE_EMBEDDING_DIMENSIONS = 1536


class Knowledge(SQLModel, table=True):
    """A diet or nutrition care manual stored for retrieval."""

    __tablename__ = "knowledge"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
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
    __table_args__ = (UniqueConstraint("knowledge_id", "chunk_index"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    knowledge_id: UUID = Field(foreign_key="knowledge.id", index=True)
    chunk_index: int
    content: str
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

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    knowledge_chunk_id: UUID = Field(foreign_key="knowledge_chunks.id", index=True)
    embedding_vector: list[float] = Field(
        sa_column=Column(
            VECTOR(KNOWLEDGE_EMBEDDING_DIMENSIONS).with_variant(JSON, "sqlite"),
            nullable=False,
        ),
    )
    model_name: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
