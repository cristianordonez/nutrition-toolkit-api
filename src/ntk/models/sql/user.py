"""Persisted application user models."""

from __future__ import annotations

import typing

from sqlalchemy import Column, String
from sqlalchemy.orm import relationship
from sqlmodel import Field, Relationship, SQLModel

if typing.TYPE_CHECKING:
    from .facility import Facility


class UserFacility(SQLModel, table=True):
    __tablename__ = "user_facility"
    user_id: int = Field(
        foreign_key="user.id",
        primary_key=True,
    )
    facility_id: int = Field(
        foreign_key="facility.id",
        primary_key=True,
    )


class User(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str | None = None
    email: str = Field(unique=True, index=True)
    facilities: list[Facility] = Relationship(
        sa_relationship=relationship(
            "Facility",
            secondary="user_facility",
            back_populates="users",
        ),
    )
    hashes: list[UserHash] = Relationship(
        sa_relationship=relationship("UserHash", back_populates="user"),
    )


class UserHash(SQLModel, table=True):
    """A stored hash associated with a user."""

    __tablename__ = "user_hash"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    hash: str = Field(sa_column=Column(String(350), nullable=False))
    user: User = Relationship(
        sa_relationship=relationship("User", back_populates="hashes"),
    )
