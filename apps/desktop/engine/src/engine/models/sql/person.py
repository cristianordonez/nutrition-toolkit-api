"""Resident identity persistence."""

from __future__ import annotations

import typing
from datetime import date, datetime  # noqa: TC003

from sqlalchemy import Index, text
from sqlalchemy.orm import relationship
from sqlmodel import Field, Relationship, SQLModel

from engine.models.clinical_facts import utc_now

if typing.TYPE_CHECKING:
    from .clinical_fact import ClinicalFact
    from .clinical_source import ClinicalSource
    from .facility import Facility
    from .ncp_note import NCPNote


def normalize_person_name_part(value: str) -> str:
    """Return a stable comparison value for one person name component."""
    return " ".join(value.split()).casefold()


def parse_person_name(name: str) -> tuple[str, str]:
    """Split common clinical display-name formats into first and last names."""
    normalized = " ".join(name.split())
    if not normalized:
        return "", ""
    if "," in normalized:
        last_name, given_names = normalized.split(",", 1)
        first_name = (
            given_names.strip().split(maxsplit=1)[0] if given_names.strip() else ""
        )
        return first_name, last_name.strip()
    parts = normalized.split()
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], parts[-1]


class Person(SQLModel, table=True):
    """A resident whose clinical assertions live in ``clinical_fact``."""

    __tablename__ = "person"
    __table_args__ = (
        Index(
            "uq_person_unscoped_identifier",
            "person_identifier",
            unique=True,
            sqlite_where=text(
                "facility_id IS NULL AND person_identifier IS NOT NULL",
            ),
        ),
        Index(
            "uq_person_facility_identifier",
            "facility_id",
            "person_identifier",
            unique=True,
            sqlite_where=text(
                "facility_id IS NOT NULL AND person_identifier IS NOT NULL",
            ),
        ),
        Index(
            "uq_person_unscoped_natural_identity",
            "normalized_first_name",
            "normalized_last_name",
            "date_of_birth",
            unique=True,
            sqlite_where=text("facility_id IS NULL AND date_of_birth IS NOT NULL"),
        ),
        Index(
            "uq_person_facility_natural_identity",
            "facility_id",
            "normalized_first_name",
            "normalized_last_name",
            "date_of_birth",
            unique=True,
            sqlite_where=text(
                "facility_id IS NOT NULL AND date_of_birth IS NOT NULL",
            ),
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    facility_id: int | None = Field(
        default=None,
        foreign_key="facility.id",
        index=True,
        ondelete="RESTRICT",
    )
    name: str
    first_name: str = ""
    last_name: str = ""
    normalized_first_name: str = Field(default="", index=True)
    normalized_last_name: str = Field(default="", index=True)
    date_of_birth: date | None = None
    person_identifier: str | None = Field(default=None, index=True)
    sex: str | None = None
    height_in: float | None = Field(default=None, gt=0)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    facility: Facility = Relationship(back_populates="people")
    clinical_sources: list[ClinicalSource] = Relationship(
        sa_relationship=relationship(
            "ClinicalSource",
            back_populates="person",
            collection_class=list,
        ),
    )
    clinical_facts: list[ClinicalFact] = Relationship(
        sa_relationship=relationship(
            "ClinicalFact",
            back_populates="person",
            collection_class=list,
        ),
    )
    ncp_notes: list[NCPNote] = Relationship(
        sa_relationship=relationship(
            "NCPNote",
            back_populates="person",
            collection_class=list,
        ),
    )

    def __init__(self, **data: typing.Any) -> None:  # noqa: ANN401
        """Normalize person identity fields for direct model construction."""
        name = " ".join(str(data.get("name") or "").split())
        first_name = " ".join(str(data.get("first_name") or "").split())
        last_name = " ".join(str(data.get("last_name") or "").split())
        if not first_name and not last_name:
            first_name, last_name = parse_person_name(name)
        if not name:
            name = " ".join(part for part in (first_name, last_name) if part)
        data.update(
            name=name,
            first_name=first_name,
            last_name=last_name,
            normalized_first_name=normalize_person_name_part(first_name),
            normalized_last_name=normalize_person_name_part(last_name),
            person_identifier=(
                " ".join(str(data.get("person_identifier") or "").split()) or None
            ),
        )
        super().__init__(**data)


__all__ = ["Person", "normalize_person_name_part", "parse_person_name"]
