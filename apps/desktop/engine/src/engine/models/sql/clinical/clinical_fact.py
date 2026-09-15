"""Narrative person clinical-fact domain model."""

from __future__ import annotations

import typing
from datetime import datetime  # noqa: TC003

from sqlalchemy import Column, Enum
from sqlmodel import Field, Relationship, SQLModel

from ntk.models.clinical_vocab import ClinicalFactType

from .common import utc_now

if typing.TYPE_CHECKING:
    from engine.models.sql.extracted_fact import ExtractedFact
    from engine.models.sql.person import Person


class PersonClinicalFact(SQLModel, table=True):
    """A narrative observation or event without a dedicated person table."""

    __tablename__ = "person_clinical_fact"
    id: int | None = Field(default=None, primary_key=True)
    person_id: int = Field(foreign_key="person.id", index=True)
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
    observed_at: datetime | None = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=utc_now, index=True)
    extracted_fact_id: int | None = Field(
        default=None,
        foreign_key="extracted_fact.id",
        index=True,
        unique=True,
    )
    person: Person = Relationship(back_populates="clinical_facts")
    extracted_fact: ExtractedFact = Relationship(
        back_populates="clinical_facts",
    )


__all__ = ["ClinicalFactType", "PersonClinicalFact"]
