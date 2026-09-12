"""Person weight-goal history model."""

from __future__ import annotations

import typing
from datetime import date, datetime  # noqa: TC003

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel

from .common import ClinicalStatus, NutritionGoalType, utc_now

if typing.TYPE_CHECKING:
    from ntk.models.sql.extracted_fact import ExtractedFact
    from ntk.models.sql.person import Person


class PersonNutritionGoal(SQLModel, table=True):
    """A source-supported nutrition goal with retained history."""

    __tablename__ = "person_nutrition_goal"
    __table_args__ = (UniqueConstraint("person_id", "state_key"),)

    id: int | None = Field(default=None, primary_key=True)
    person_id: int = Field(foreign_key="person.id", index=True)
    goal_type: NutritionGoalType = Field(index=True)
    target_value: float | None = None
    target_unit: str | None = None
    target_date: date | None = Field(default=None, index=True)
    notes: str | None = None
    status: ClinicalStatus = Field(default=ClinicalStatus.UNKNOWN, index=True)
    effective_at: datetime | None = Field(default=None, index=True)
    discontinued_at: datetime | None = Field(default=None, index=True)
    observed_at: datetime | None = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=utc_now, index=True)
    state_key: str = Field(max_length=64, index=True)
    extracted_fact_id: int | None = Field(
        default=None,
        foreign_key="extracted_fact.id",
        nullable=False,
        index=True,
        unique=True,
    )
    person: Person = Relationship(back_populates="nutrition_goals")
    extracted_fact: ExtractedFact = Relationship(back_populates="nutrition_goals")


__all__ = ["PersonNutritionGoal"]
