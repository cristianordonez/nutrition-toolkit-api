"""Person oral and dentition status domain model."""

from __future__ import annotations

import typing
from datetime import datetime  # noqa: TC003

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel

from .common import (
    ClinicalStatus,
    DentitionStatus,
    DentureStatus,
    utc_now,
)

if typing.TYPE_CHECKING:
    from ntk.models.sql.extracted_fact import ExtractedFact
    from ntk.models.sql.person import Person


class PersonOralFeedingStatus(SQLModel, table=True):
    """A person's nutrition-relevant oral and denture state."""

    __tablename__ = "person_oral_feeding_status"
    __table_args__ = (UniqueConstraint("person_id", "state_key"),)

    id: int | None = Field(default=None, primary_key=True)
    person_id: int = Field(foreign_key="person.id", index=True)
    dentition_status: DentitionStatus | None = Field(default=None, index=True)
    upper_denture: DentureStatus | None = None
    lower_denture: DentureStatus | None = None
    chewing_difficulty: bool | None = None
    swallowing_difficulty: bool | None = None
    dysphagia: bool | None = None
    aspiration_risk: bool | None = None
    slp_following: bool | None = None
    notes: str | None = None
    status: ClinicalStatus = Field(default=ClinicalStatus.UNKNOWN, index=True)
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
    person: Person = Relationship(back_populates="oral_feeding_status_history")
    extracted_fact: ExtractedFact = Relationship(
        back_populates="oral_feeding_status_history",
    )


__all__ = ["PersonOralFeedingStatus"]
