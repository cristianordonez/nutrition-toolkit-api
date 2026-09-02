"""Resident edema domain model."""

from __future__ import annotations

import typing
from datetime import datetime  # noqa: TC003

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel

if typing.TYPE_CHECKING:
    from ntk.models.sql.extracted_fact import ExtractedFact
    from ntk.models.sql.resident import Resident


class ResidentEdema(SQLModel, table=True):
    """A persisted resident edema observation."""

    __tablename__ = "resident_edema"
    __table_args__ = (UniqueConstraint("resident_id", "location", "observed_at"),)
    id: int | None = Field(default=None, primary_key=True)
    resident_id: int = Field(foreign_key="resident.id", index=True)
    resident_facility_stay_id: int | None = Field(
        default=None,
        foreign_key="resident_facility_stay.id",
    )
    location: str
    severity: str | None = None
    observed_at: datetime = Field(index=True)
    extracted_fact_id: int | None = Field(
        default=None,
        foreign_key="extracted_fact.id",
        index=True,
    )
    resident: Resident = Relationship(back_populates="edema")
    extracted_fact: ExtractedFact = Relationship(back_populates="edema")


__all__ = ["ResidentEdema"]
