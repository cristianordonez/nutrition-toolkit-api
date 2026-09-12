from __future__ import annotations

import typing

from sqlalchemy.orm import relationship
from sqlmodel import Field, Relationship, SQLModel

if typing.TYPE_CHECKING:
    from .document import Document
    from .person import Person


class Facility(SQLModel, table=True):
    """A care facility containing persons and users."""

    __tablename__ = "facility"

    id: int | None = Field(default=None, primary_key=True)
    facility_identifier: str | None = Field(default=None, unique=True, index=True)
    name: str
    normalized_name: str = Field(default="", unique=True, index=True)
    persons: list[Person] = Relationship(
        sa_relationship=relationship("Person", back_populates="facility"),
    )
    documents: list[Document] = Relationship(
        sa_relationship=relationship("Document", back_populates="facility"),
    )

    def __init__(self, **data: typing.Any) -> None:  # noqa: ANN401
        """Normalize facility identity fields for direct model construction."""
        name = " ".join(str(data.get("name") or "").split())
        identifier = " ".join(str(data.get("facility_identifier") or "").split())
        data.update(
            name=name,
            normalized_name=normalize_facility_name(name),
            facility_identifier=identifier or None,
        )
        super().__init__(**data)


def normalize_facility_name(value: str) -> str:
    """Return the stable comparison value for a facility name or alias."""
    return " ".join(value.split()).casefold()
