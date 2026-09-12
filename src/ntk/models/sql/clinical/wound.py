"""Person wound domain model."""

from __future__ import annotations

import typing
from datetime import datetime  # noqa: TC003

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel

from .common import utc_now

if typing.TYPE_CHECKING:
    from ntk.models.sql.extracted_fact import ExtractedFact
    from ntk.models.sql.person import Person


class PersonWound(SQLModel, table=True):
    """A persisted person wound observation."""

    __tablename__ = "person_wound"
    __table_args__ = (UniqueConstraint("person_id", "wound_number", "observed_at"),)
    id: int | None = Field(default=None, primary_key=True)
    person_id: int = Field(foreign_key="person.id", index=True)
    wound_number: str | None = Field(default=None, index=True)
    type: str
    location: str
    weeks_in_treatment: int | None = None
    progress: str | None = None
    stage: str | None = None
    size: str | None = None
    assessment_note: str | None = None
    physician_orders: str | None = None
    physician_orders_notes: str | None = None
    observed_at: datetime = Field(index=True)
    created_at: datetime = Field(default_factory=utc_now, index=True)
    person: Person = Relationship(back_populates="wounds")
    extracted_fact_id: int | None = Field(
        default=None,
        foreign_key="extracted_fact.id",
        index=True,
    )
    extracted_fact: ExtractedFact = Relationship(back_populates="wounds")


__all__ = ["PersonWound"]
