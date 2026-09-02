"""Resident meal-intake domain model."""

from __future__ import annotations

import typing
from datetime import datetime  # noqa: TC003

from sqlmodel import Field, Relationship, SQLModel

if typing.TYPE_CHECKING:
    from ntk.models.sql.extracted_fact import ExtractedFact
    from ntk.models.sql.resident import Resident


class ResidentMealIntake(SQLModel, table=True):
    """A persisted resident meal-intake observation."""

    __tablename__ = "resident_meal_intake"
    id: int | None = Field(default=None, primary_key=True)
    resident_id: int = Field(foreign_key="resident.id", index=True)
    resident_facility_stay_id: int | None = Field(
        default=None,
        foreign_key="resident_facility_stay.id",
    )
    min_percent: float | None = None
    max_percent: float | None = None
    appetite: str | None = None
    observed_at: datetime = Field(index=True)
    extracted_fact_id: int | None = Field(
        default=None,
        foreign_key="extracted_fact.id",
        index=True,
    )
    resident: Resident = Relationship(back_populates="meal_intakes")
    extracted_fact: ExtractedFact = Relationship(back_populates="meal_intakes")


__all__ = ["ResidentMealIntake"]
