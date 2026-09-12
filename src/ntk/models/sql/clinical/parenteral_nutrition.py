"""Parenteral nutrition prescription model."""

from __future__ import annotations

import typing
from datetime import datetime, time  # noqa: TC003

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel

from .common import (
    LipidDeliveryType,
    ParenteralAccessRoute,
    ParenteralFormulaType,
    ParenteralNutritionStatus,
    utc_now,
)

if typing.TYPE_CHECKING:
    from ntk.models.sql.extracted_fact import ExtractedFact
    from ntk.models.sql.person import Person


class PersonParenteralNutrition(SQLModel, table=True):
    """Documented PN prescription inputs without calculated nutrition totals."""

    __tablename__ = "person_parenteral_nutrition"
    __table_args__ = (UniqueConstraint("person_id", "state_key"),)

    id: int | None = Field(default=None, primary_key=True)
    person_id: int = Field(foreign_key="person.id", index=True)
    access_route: ParenteralAccessRoute | None = Field(default=None, index=True)
    access_description: str | None = None
    formula_type: ParenteralFormulaType | None = Field(default=None, index=True)
    total_volume_ml: float | None = Field(default=None, gt=0)
    rate_ml_hr: float | None = Field(default=None, gt=0)
    daily_start_time: time | None = None
    hours_per_day: float | None = Field(default=None, gt=0, le=24)
    dextrose_g_per_l: float | None = Field(default=None, ge=0)
    amino_acid_g_per_l: float | None = Field(default=None, ge=0)
    documented_protein_g: float | None = Field(default=None, ge=0)
    documented_calories_kcal: float | None = Field(default=None, ge=0)
    lipid_delivery: LipidDeliveryType | None = Field(default=None, index=True)
    lipid_concentration_percent: float | None = Field(default=None, gt=0, le=100)
    lipid_total_volume_ml: float | None = Field(default=None, gt=0)
    lipid_run_time_hours: float | None = Field(default=None, gt=0, le=24)
    lipid_rate_ml_hr: float | None = Field(default=None, gt=0)
    instructions: str | None = None
    status: ParenteralNutritionStatus = Field(
        default=ParenteralNutritionStatus.UNKNOWN,
        index=True,
    )
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
    person: Person = Relationship(back_populates="parenteral_nutrition_records")
    extracted_fact: ExtractedFact = Relationship(
        back_populates="parenteral_nutrition_records",
    )


__all__ = ["PersonParenteralNutrition"]
