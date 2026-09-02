"""Narrative resident clinical-fact domain model."""

from __future__ import annotations

import typing
from datetime import datetime  # noqa: TC003
from enum import StrEnum

from sqlalchemy import Column, Enum
from sqlmodel import Field, Relationship, SQLModel

if typing.TYPE_CHECKING:
    from ntk.models.sql.extracted_fact import ExtractedFact
    from ntk.models.sql.resident import Resident


class ClinicalFactType(StrEnum):
    """Classify a resident clinical fact as an observation or event."""

    OBSERVATION = "observation"
    EVENT = "event"


class ResidentClinicalFact(SQLModel, table=True):
    """A narrative observation or event without a dedicated resident table."""

    __tablename__ = "resident_clinical_fact"
    id: int | None = Field(default=None, primary_key=True)
    resident_id: int = Field(foreign_key="resident.id", index=True)
    resident_facility_stay_id: int | None = Field(
        default=None,
        foreign_key="resident_facility_stay.id",
    )
    clinical_fact_type: ClinicalFactType = Field(
        sa_column=Column(
            Enum(
                ClinicalFactType,
                name="clinical_fact_type",
                values_callable=lambda enum_type: [item.value for item in enum_type],
            ),
            nullable=False,
            index=True,
        ),
    )
    observation_type: str = Field(index=True)
    status: str | None = None
    severity: str | None = None
    description: str | None = None
    observed_at: datetime = Field(index=True)
    extracted_fact_id: int | None = Field(
        default=None,
        foreign_key="extracted_fact.id",
        index=True,
        unique=True,
    )
    resident: Resident = Relationship(back_populates="clinical_facts")
    extracted_fact: ExtractedFact = Relationship(
        back_populates="clinical_facts",
    )


__all__ = ["ClinicalFactType", "ResidentClinicalFact"]
