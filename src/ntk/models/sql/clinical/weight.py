"""Person weight domain model."""

from __future__ import annotations

import typing
from datetime import datetime  # noqa: TC003

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel

from .common import WeightContext, utc_now

if typing.TYPE_CHECKING:
    from ntk.models.sql.extracted_fact import ExtractedFact
    from ntk.models.sql.person import Person


class PersonWeight(SQLModel, table=True):
    """A persisted person weight observation."""

    __tablename__ = "person_weight"
    __table_args__ = (UniqueConstraint("person_id", "measured_at"),)
    id: int | None = Field(default=None, primary_key=True)
    person_id: int = Field(foreign_key="person.id", index=True)
    measured_at: datetime = Field(index=True)
    weight_lb: float
    description: str | None = None
    weight_context: WeightContext | None = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=utc_now, index=True)
    extracted_fact_id: int | None = Field(
        default=None,
        foreign_key="extracted_fact.id",
        index=True,
    )
    person: Person = Relationship(back_populates="weights")
    extracted_fact: ExtractedFact = Relationship(back_populates="weights")


__all__ = ["PersonWeight"]
