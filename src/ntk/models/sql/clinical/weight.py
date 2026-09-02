"""Resident weight domain model."""

from __future__ import annotations

import typing
from datetime import datetime  # noqa: TC003

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel

if typing.TYPE_CHECKING:
    from ntk.models.sql.extracted_fact import ExtractedFact
    from ntk.models.sql.resident import Resident


class ResidentWeight(SQLModel, table=True):
    """A persisted resident weight observation."""

    __tablename__ = "resident_weight"
    __table_args__ = (UniqueConstraint("resident_id", "measured_at"),)
    id: int | None = Field(default=None, primary_key=True)
    resident_id: int = Field(foreign_key="resident.id", index=True)
    resident_facility_stay_id: int | None = Field(
        default=None,
        foreign_key="resident_facility_stay.id",
    )
    measured_at: datetime | None = Field(default=None, index=True)
    weight_lb: float
    description: str | None = None
    extracted_fact_id: int | None = Field(
        default=None,
        foreign_key="extracted_fact.id",
        index=True,
    )
    resident: Resident = Relationship(back_populates="weights")
    extracted_fact: ExtractedFact = Relationship(back_populates="weights")


__all__ = ["ResidentWeight"]
