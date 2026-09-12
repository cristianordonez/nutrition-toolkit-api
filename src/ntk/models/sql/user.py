"""Persisted application user models."""

from __future__ import annotations

from sqlalchemy import Column, String
from sqlalchemy.orm import relationship
from sqlmodel import Field, Relationship, SQLModel


class User(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str | None = None
    email: str = Field(unique=True, index=True)
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
