"""Nutrition-relevant gastrointestinal observation model."""

from __future__ import annotations

import typing
from datetime import datetime  # noqa: TC003

from sqlmodel import Field, Relationship, SQLModel

from .common import GISymptom, utc_now

if typing.TYPE_CHECKING:
    from ntk.models.sql.extracted_fact import ExtractedFact
    from ntk.models.sql.person import Person


class PersonGIObservation(SQLModel, table=True):
    """A time-series gastrointestinal symptom observation."""

    __tablename__ = "person_gi_observation"
    id: int | None = Field(default=None, primary_key=True)
    person_id: int = Field(foreign_key="person.id", index=True)
    symptom: GISymptom = Field(index=True)
    severity: str | None = None
    notes: str | None = None
    observed_at: datetime | None = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=utc_now, index=True)
    observation_key: str = Field(max_length=64, index=True)
    extracted_fact_id: int | None = Field(
        default=None,
        foreign_key="extracted_fact.id",
        nullable=False,
        index=True,
        unique=True,
    )
    person: Person = Relationship(back_populates="gi_observations")
    extracted_fact: ExtractedFact = Relationship(back_populates="gi_observations")


__all__ = ["PersonGIObservation"]
