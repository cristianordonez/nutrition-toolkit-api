"""The diet and nutrition-care manuals, stored on the device for retrieval.

Reference content, not patient content. Every other table in this database
describes one device's residents; these three describe published manuals that
are identical on every install, ship inside the application bundle, and carry
no PHI. Keeping them in their own tables is what lets a factory reset, a
backup, or a "delete all patient data" act on one set without touching the
other.

Ported from the server's pgvector version. The shape is the same; the vector
is a packed ``float32`` BLOB rather than a ``VECTOR`` column, scored directly
at search time rather than through a separate index.
"""

from __future__ import annotations

from datetime import datetime  # noqa: TC003
from enum import StrEnum

from sqlalchemy.orm import relationship
from sqlmodel import Field, Relationship, SQLModel, UniqueConstraint

from engine.models.clinical_facts import utc_now


class KnowledgeType(StrEnum):
    """The published manuals the agent may consult."""

    DIET_MANUAL = "diet-manual"
    NUTRITION_CARE_MANUAL = "nutrition-care-manual"


class Knowledge(SQLModel, table=True):
    """One manual stored for retrieval."""

    __tablename__ = "knowledge"

    id: int | None = Field(default=None, primary_key=True)
    filename: str
    knowledge_type: KnowledgeType = Field(index=True)
    #: Identifies the exact source file a chunk came from, so a rebuilt bundle
    #: can tell a changed manual from an unchanged one.
    file_hash: str = Field(index=True)
    synced_at: datetime = Field(default_factory=utc_now)
    chunks: list[KnowledgeChunk] = Relationship(
        # ``collection_class`` is not decoration: the relationship is declared
        # by string, so without it SQLAlchemy treats this as scalar and warns
        # that a manual has "multiple rows for a uselist=False attribute".
        sa_relationship=relationship(
            "KnowledgeChunk",
            back_populates="knowledge",
            collection_class=list,
        ),
    )


class KnowledgeChunk(SQLModel, table=True):
    """A bounded passage of a manual, sized for retrieval."""

    __tablename__ = "knowledge_chunk"
    __table_args__ = (UniqueConstraint("knowledge_id", "chunk_index"),)

    id: int | None = Field(default=None, primary_key=True)
    knowledge_id: int = Field(foreign_key="knowledge.id", index=True)
    chunk_index: int
    content: str
    section_title: str | None = None
    source_page_start: int | None = None
    source_page_end: int | None = None
    created_at: datetime = Field(default_factory=utc_now)
    knowledge: Knowledge = Relationship(
        sa_relationship=relationship("Knowledge", back_populates="chunks"),
    )


class KnowledgeChunkEmbedding(SQLModel, table=True):
    """One chunk's embedding under one model.

    ``model`` and ``dimensions`` are per row for the same reason they are on
    ``NCPNoteEmbedding``: vectors from different models are not comparable, so
    a search filters to the model it is querying with instead of silently
    ranking across them. It matters more here -- the bundled manuals are
    embedded at build time with one model, and a device configured for the
    other must re-embed rather than compare against them.
    """

    __tablename__ = "knowledge_chunk_embedding"

    id: int | None = Field(default=None, primary_key=True)
    knowledge_chunk_id: int = Field(
        foreign_key="knowledge_chunk.id",
        index=True,
    )
    model: str = Field(index=True)
    dimensions: int
    vector: bytes
    created_at: datetime = Field(default_factory=utc_now)


__all__ = [
    "Knowledge",
    "KnowledgeChunk",
    "KnowledgeChunkEmbedding",
    "KnowledgeType",
]
