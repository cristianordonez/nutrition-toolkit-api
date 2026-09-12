"""Daily fluid target or restriction model."""

from __future__ import annotations

import typing
from datetime import datetime  # noqa: TC003

from pydantic import model_validator
from sqlalchemy import UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel

from .common import ClinicalStatus, utc_now

if typing.TYPE_CHECKING:
    from ntk.models.sql.extracted_fact import ExtractedFact
    from ntk.models.sql.person import Person


class PersonFluidPlan(SQLModel, table=True):
    """A documented overall fluid target, restriction, or both."""

    __tablename__ = "person_fluid_plan"
    __table_args__ = (UniqueConstraint("person_id", "state_key"),)

    id: int | None = Field(default=None, primary_key=True)
    person_id: int = Field(foreign_key="person.id", index=True)
    target_ml_day: float | None = Field(default=None, ge=0)
    restriction_ml_day: float | None = Field(default=None, ge=0)
    instructions: str | None = None
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
    person: Person = Relationship(back_populates="fluid_plans")
    extracted_fact: ExtractedFact = Relationship(back_populates="fluid_plans")

    @model_validator(mode="after")
    def validate_plan(self) -> typing.Self:
        """Require at least one structured value or meaningful instruction."""
        if (
            self.target_ml_day is None
            and self.restriction_ml_day is None
            and not (self.instructions or "").strip()
        ):
            message = "A fluid plan requires a target, restriction, or instructions"
            raise ValueError(message)
        return self


__all__ = ["PersonFluidPlan"]
