"""Person allergy domain model."""

from __future__ import annotations

import typing
from datetime import datetime  # noqa: TC003

from sqlalchemy import CheckConstraint, UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel

from .common import ClinicalStatus, utc_now

if typing.TYPE_CHECKING:
    from ntk.models.sql.extracted_fact import ExtractedFact
    from ntk.models.sql.person import Person


class PersonAllergy(SQLModel, table=True):
    """A documented allergy or an explicit no-known-allergies declaration."""

    __tablename__ = "person_allergy"
    __table_args__ = (
        CheckConstraint(
            "(allergen IS NOT NULL AND no_known_allergies = false) OR "
            "(allergen IS NULL AND no_known_allergies = true)",
            name="ck_person_allergy_subject",
        ),
        UniqueConstraint("person_id", "state_key"),
    )

    id: int | None = Field(default=None, primary_key=True)
    person_id: int = Field(foreign_key="person.id", index=True)
    allergen: str | None = Field(default=None, index=True)
    reaction: str | None = None
    no_known_allergies: bool = False
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
    person: Person = Relationship(back_populates="allergies")
    extracted_fact: ExtractedFact = Relationship(back_populates="allergies")


__all__ = ["PersonAllergy"]
