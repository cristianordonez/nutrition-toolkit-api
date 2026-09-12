"""Person edema domain model."""

from __future__ import annotations

import typing
from datetime import datetime  # noqa: TC003

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel

from .common import utc_now

if typing.TYPE_CHECKING:
    from ntk.models.sql.extracted_fact import ExtractedFact
    from ntk.models.sql.person import Person


class PersonEdema(SQLModel, table=True):
    """A persisted person edema observation."""

    __tablename__ = "person_edema"
    __table_args__ = (UniqueConstraint("person_id", "location", "observed_at"),)
    id: int | None = Field(default=None, primary_key=True)
    person_id: int = Field(foreign_key="person.id", index=True)
    location: str
    severity: str | None = None
    observed_at: datetime = Field(index=True)
    created_at: datetime = Field(default_factory=utc_now, index=True)
    extracted_fact_id: int | None = Field(
        default=None,
        foreign_key="extracted_fact.id",
        index=True,
    )
    person: Person = Relationship(back_populates="edema")
    extracted_fact: ExtractedFact = Relationship(back_populates="edema")


__all__ = ["PersonEdema"]
