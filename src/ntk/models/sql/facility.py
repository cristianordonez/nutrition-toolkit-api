from __future__ import annotations

import typing

from sqlalchemy.orm import relationship
from sqlmodel import Field, Relationship, SQLModel

if typing.TYPE_CHECKING:
    from .resident import ResidentFacilityStay
    from .user import User


class Facility(SQLModel, table=True):
    """A care facility containing residents and users."""

    __tablename__ = "facility"

    id: int | None = Field(default=None, primary_key=True)
    facility_id: str = Field(unique=True, index=True)
    name: str
    users: list[User] = Relationship(
        sa_relationship=relationship(
            "User",
            secondary="user_facility",
            back_populates="facilities",
        ),
    )
    resident_stays: list[ResidentFacilityStay] = Relationship(
        sa_relationship=relationship("ResidentFacilityStay", back_populates="facility"),
    )
