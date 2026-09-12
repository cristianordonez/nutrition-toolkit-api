"""Person diagnosis domain model."""

from __future__ import annotations

import typing
from datetime import datetime  # noqa: TC003

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel

from .common import ClinicalStatus, utc_now

if typing.TYPE_CHECKING:
    from ntk.models.sql.extracted_fact import ExtractedFact
    from ntk.models.sql.person import Person


class PersonDiagnosis(SQLModel, table=True):
    """A source-supported person diagnosis without inferred terminology codes."""

    __tablename__ = "person_diagnosis"
    __table_args__ = (UniqueConstraint("person_id", "state_key"),)

    id: int | None = Field(default=None, primary_key=True)
    person_id: int = Field(foreign_key="person.id", index=True)
    diagnosis: str = Field(index=True)
    code: str | None = Field(default=None, index=True)
    code_system: str | None = None
    status: ClinicalStatus = Field(default=ClinicalStatus.UNKNOWN, index=True)
    observed_at: datetime | None = Field(default=None, index=True)
    effective_at: datetime | None = Field(default=None, index=True)
    discontinued_at: datetime | None = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=utc_now, index=True)
    state_key: str = Field(max_length=64, index=True)
    extracted_fact_id: int | None = Field(
        default=None,
        foreign_key="extracted_fact.id",
        nullable=False,
        index=True,
        unique=True,
    )
    person: Person = Relationship(back_populates="diagnoses")
    extracted_fact: ExtractedFact = Relationship(back_populates="diagnoses")


__all__ = ["PersonDiagnosis"]
