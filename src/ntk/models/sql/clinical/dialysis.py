"""Person dialysis domain model."""

from __future__ import annotations

import typing
from datetime import datetime  # noqa: TC003

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel

from .common import ClinicalStatus, DialysisType, utc_now

if typing.TYPE_CHECKING:
    from ntk.models.sql.extracted_fact import ExtractedFact
    from ntk.models.sql.person import Person


class PersonDialysis(SQLModel, table=True):
    """A nutrition-relevant dialysis state and documented schedule."""

    __tablename__ = "person_dialysis"
    __table_args__ = (UniqueConstraint("person_id", "state_key"),)

    id: int | None = Field(default=None, primary_key=True)
    person_id: int = Field(foreign_key="person.id", index=True)
    dialysis_type: DialysisType | None = Field(default=None, index=True)
    schedule: str | None = None
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
    person: Person = Relationship(back_populates="dialysis_records")
    extracted_fact: ExtractedFact = Relationship(back_populates="dialysis_records")


__all__ = ["PersonDialysis"]
