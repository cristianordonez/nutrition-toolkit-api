"""Resident laboratory-result domain model."""

from __future__ import annotations

import typing
from datetime import datetime  # noqa: TC003

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel

if typing.TYPE_CHECKING:
    from ntk.models.sql.extracted_fact import ExtractedFact
    from ntk.models.sql.resident import Resident


class ResidentLab(SQLModel, table=True):
    """A persisted resident laboratory result."""

    __tablename__ = "resident_lab"
    __table_args__ = (UniqueConstraint("resident_id", "name", "observed_at"),)
    id: int | None = Field(default=None, primary_key=True)
    resident_id: int = Field(foreign_key="resident.id", index=True)
    resident_facility_stay_id: int | None = Field(
        default=None,
        foreign_key="resident_facility_stay.id",
    )
    name: str
    result: str
    unit: str | None = None
    flag: str | None = None
    reference_range: str | None = None
    observed_at: datetime = Field(index=True)
    resident: Resident = Relationship(back_populates="labs")
    extracted_fact_id: int | None = Field(
        default=None,
        foreign_key="extracted_fact.id",
        index=True,
    )
    extracted_fact: ExtractedFact = Relationship(back_populates="labs")


__all__ = ["ResidentLab"]
