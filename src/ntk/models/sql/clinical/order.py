"""Resident order domain model."""

from __future__ import annotations

import typing
from datetime import date  # noqa: TC003

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel

if typing.TYPE_CHECKING:
    from ntk.models.sql.extracted_fact import ExtractedFact
    from ntk.models.sql.resident import Resident


class ResidentOrder(SQLModel, table=True):
    """A persisted resident order."""

    __tablename__ = "resident_order"
    __table_args__ = (UniqueConstraint("resident_id", "summary", "revision_date"),)
    id: int | None = Field(default=None, primary_key=True)
    resident_id: int = Field(foreign_key="resident.id", index=True)
    resident_facility_stay_id: int | None = Field(
        default=None,
        foreign_key="resident_facility_stay.id",
    )
    summary: str
    category: str | None = None
    status: str | None = None
    revision_date: date | None = None
    supply_last_order_date: date | None = None
    supply_reorder: str | None = None
    resident: Resident = Relationship(back_populates="orders")
    extracted_fact_id: int | None = Field(
        default=None,
        foreign_key="extracted_fact.id",
        index=True,
    )
    extracted_fact: ExtractedFact = Relationship(back_populates="orders")


__all__ = ["ResidentOrder"]
