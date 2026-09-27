"""Minimal facility persistence for resident scoping."""

from __future__ import annotations

import typing
from datetime import datetime  # noqa: TC003

from sqlalchemy.orm import relationship
from sqlmodel import Field, Relationship, SQLModel

from engine.models.clinical_facts import utc_now

if typing.TYPE_CHECKING:
    from .document import Document
    from .ncp_note import NCPNote
    from .person import Person


class Facility(SQLModel, table=True):
    """A facility identity; workflow and configuration are intentionally absent."""

    __tablename__ = "facility"

    id: int | None = Field(default=None, primary_key=True)
    facility_identifier: str | None = Field(default=None, index=True, unique=True)
    name: str
    normalized_name: str = Field(index=True, unique=True)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    people: list[Person] = Relationship(
        sa_relationship=relationship(
            "Person",
            back_populates="facility",
            collection_class=list,
        ),
    )
    documents: list[Document] = Relationship(
        sa_relationship=relationship(
            "Document",
            back_populates="facility",
            collection_class=list,
        ),
    )
    ncp_notes: list[NCPNote] = Relationship(
        sa_relationship=relationship(
            "NCPNote",
            back_populates="facility",
            collection_class=list,
        ),
    )


__all__ = ["Facility"]
