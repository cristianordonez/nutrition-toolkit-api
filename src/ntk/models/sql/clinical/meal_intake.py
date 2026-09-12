"""Person meal-intake domain model."""

from __future__ import annotations

import typing
from datetime import datetime  # noqa: TC003

from sqlmodel import Field, Relationship, SQLModel

from .common import utc_now

if typing.TYPE_CHECKING:
    from ntk.models.sql.extracted_fact import ExtractedFact
    from ntk.models.sql.person import Person


class PersonMealIntake(SQLModel, table=True):
    """A persisted person meal-intake observation."""

    __tablename__ = "person_meal_intake"
    id: int | None = Field(default=None, primary_key=True)
    person_id: int = Field(foreign_key="person.id", index=True)
    min_percent: float | None = None
    max_percent: float | None = None
    observed_at: datetime = Field(index=True)
    created_at: datetime = Field(default_factory=utc_now, index=True)
    extracted_fact_id: int | None = Field(
        default=None,
        foreign_key="extracted_fact.id",
        index=True,
    )
    person: Person = Relationship(back_populates="meal_intakes")
    extracted_fact: ExtractedFact = Relationship(back_populates="meal_intakes")


__all__ = ["PersonMealIntake"]
