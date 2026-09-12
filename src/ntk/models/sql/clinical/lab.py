"""Person laboratory-result domain model."""

from __future__ import annotations

import typing
from datetime import datetime  # noqa: TC003

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel

from .common import utc_now

if typing.TYPE_CHECKING:
    from ntk.models.sql.extracted_fact import ExtractedFact
    from ntk.models.sql.person import Person


class PersonLab(SQLModel, table=True):
    """A persisted person laboratory result."""

    __tablename__ = "person_lab"
    __table_args__ = (UniqueConstraint("person_id", "name", "observed_at"),)
    id: int | None = Field(default=None, primary_key=True)
    person_id: int = Field(foreign_key="person.id", index=True)
    name: str
    result: str
    unit: str | None = None
    flag: str | None = None
    reference_range: str | None = None
    observed_at: datetime = Field(index=True)
    created_at: datetime = Field(default_factory=utc_now, index=True)
    person: Person = Relationship(back_populates="labs")
    extracted_fact_id: int | None = Field(
        default=None,
        foreign_key="extracted_fact.id",
        index=True,
    )
    extracted_fact: ExtractedFact = Relationship(back_populates="labs")


__all__ = ["PersonLab"]
