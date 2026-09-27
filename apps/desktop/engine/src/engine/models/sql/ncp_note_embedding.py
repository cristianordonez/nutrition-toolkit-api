"""Local embeddings belonging to persisted NCP notes."""

from __future__ import annotations

import typing
from datetime import datetime  # noqa: TC003

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel

from engine.models.clinical_facts import utc_now
from engine.utils.vector import unpack_vector

if typing.TYPE_CHECKING:
    from .ncp_note import NCPNote


class NCPNoteEmbedding(SQLModel, table=True):
    """One NCP note's vector under one local embedding model."""

    __tablename__ = "ncp_note_embedding"
    __table_args__ = (
        UniqueConstraint(
            "ncp_note_id",
            "model",
            name="uq_ncp_note_embedding_model",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    ncp_note_id: int = Field(
        foreign_key="ncp_note.id",
        index=True,
        ondelete="CASCADE",
    )
    model: str = Field(index=True)
    dimensions: int
    vector: bytes
    created_at: datetime = Field(default_factory=utc_now)
    note: NCPNote = Relationship(back_populates="embeddings")

    def to_list(self) -> list[float]:
        """Unpack the persisted float32 vector."""
        return unpack_vector(self.vector)


__all__ = ["NCPNoteEmbedding"]
