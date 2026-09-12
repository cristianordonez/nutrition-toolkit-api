"""Person diet domain model."""

from __future__ import annotations

import typing
from datetime import datetime  # noqa: TC003

from pydantic import field_validator
from sqlalchemy import JSON, Column, UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel

from ntk.models.sql.food import LiquidConsistency  # noqa: TC001

from .common import (
    ClinicalStatus,
    normalize_diet_restriction,
    normalize_diet_texture,
    normalize_diet_type,
    utc_now,
)

if typing.TYPE_CHECKING:
    from ntk.models.sql.extracted_fact import ExtractedFact
    from ntk.models.sql.person import Person


class PersonDiet(SQLModel, table=True):
    """A normalized prescribed diet state with texture kept separate."""

    __tablename__ = "person_diet"
    __table_args__ = (UniqueConstraint("person_id"),)

    id: int | None = Field(default=None, primary_key=True)
    person_id: int = Field(foreign_key="person.id", index=True)
    diet_type: str | None = Field(default=None, index=True)
    texture: str | None = Field(default=None, index=True)
    liquid_consistency: LiquidConsistency | None = Field(default=None, index=True)
    restrictions: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )
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
    person: Person = Relationship(back_populates="diets")
    extracted_fact: ExtractedFact = Relationship(back_populates="diets")

    @field_validator("diet_type", mode="before")
    @classmethod
    def canonicalize_diet_type(cls, value: object) -> object:
        """Keep directly constructed diet rows aligned with ingestion."""
        return normalize_diet_type(value) if isinstance(value, str) else value

    @field_validator("texture", mode="before")
    @classmethod
    def canonicalize_texture(cls, value: object) -> object:
        """Keep directly constructed texture values aligned with ingestion."""
        return normalize_diet_texture(value) if isinstance(value, str) else value

    @field_validator("restrictions", mode="before")
    @classmethod
    def canonicalize_restrictions(cls, value: object) -> object:
        """Keep directly constructed restrictions aligned with ingestion."""
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, (list, tuple, set)):
            return value
        normalized = [
            normalize_diet_restriction(item)
            for item in value
            if isinstance(item, str) and item.strip()
        ]
        return list(dict.fromkeys(normalized))


__all__ = ["PersonDiet"]
