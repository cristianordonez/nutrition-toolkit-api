"""Person miscellaneous order fallback model."""

from __future__ import annotations

import typing
from datetime import datetime  # noqa: TC003

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel

from .common import ClinicalStatus, utc_now

if typing.TYPE_CHECKING:
    from ntk.models.sql.extracted_fact import ExtractedFact
    from ntk.models.sql.person import Person


class PersonMiscOrder(SQLModel, table=True):
    """A legitimate order outside the normalized nutrition-related domains."""

    __tablename__ = "person_misc_order"
    __table_args__ = (UniqueConstraint("person_id", "state_key"),)

    id: int | None = Field(default=None, primary_key=True)
    person_id: int = Field(foreign_key="person.id", index=True)
    order_type: str | None = Field(default=None, index=True)
    description: str
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
    person: Person = Relationship(back_populates="misc_orders")
    extracted_fact: ExtractedFact = Relationship(back_populates="misc_orders")


__all__ = ["PersonMiscOrder"]
