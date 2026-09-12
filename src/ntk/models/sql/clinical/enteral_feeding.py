"""Person enteral-feeding domain model."""

from __future__ import annotations

import typing
from datetime import datetime  # noqa: TC003

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel

from ntk.models.sql.food import PackageType  # noqa: TC001

from .common import ClinicalStatus, FeedingMethod, utc_now

if typing.TYPE_CHECKING:
    from ntk.models.sql.extracted_fact import ExtractedFact
    from ntk.models.sql.person import Person


class PersonEnteralFeeding(SQLModel, table=True):
    """Documented inputs for a continuous, cyclic, or bolus tube feeding."""

    __tablename__ = "person_enteral_feeding"
    __table_args__ = (UniqueConstraint("person_id", "state_key"),)

    id: int | None = Field(default=None, primary_key=True)
    person_id: int = Field(foreign_key="person.id", index=True)
    formula: str | None = Field(default=None, index=True)
    route: str | None = None
    feeding_method: FeedingMethod | None = Field(default=None, index=True)
    rate_ml_hr: float | None = Field(default=None, gt=0)
    hours_per_day: float | None = Field(default=None, gt=0, le=24)
    bolus_volume_ml: float | None = Field(default=None, gt=0)
    boluses_per_day: int | None = Field(default=None, gt=0)
    flush_ml: float | None = Field(default=None, ge=0)
    flush_frequency_hours: float | None = Field(default=None, gt=0)
    flush_instructions: str | None = None
    feeding_schedule: str | None = None
    package_type: PackageType | None = Field(default=None, index=True)
    package_volume_ml: float | None = Field(default=None, gt=0)
    caloric_density_kcal_ml: float | None = Field(default=None, gt=0)
    instructions: str | None = None
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
    person: Person = Relationship(back_populates="enteral_feedings")
    extracted_fact: ExtractedFact = Relationship(back_populates="enteral_feedings")


__all__ = ["PersonEnteralFeeding"]
