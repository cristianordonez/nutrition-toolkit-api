"""Persistent application preferences in the main SQLite database."""

from __future__ import annotations

from sqlalchemy import CheckConstraint
from sqlmodel import Field, SQLModel

SINGLETON_ID = 1


class ApplicationSettings(SQLModel, table=True):
    """Singleton preferences for the person using this desktop application."""

    __tablename__ = "settings"
    __table_args__ = (
        CheckConstraint(f"id = {SINGLETON_ID}", name="ck_settings_singleton"),
    )

    id: int | None = Field(default=SINGLETON_ID, primary_key=True)
    full_name: str | None = None
    credentials: str | None = None
    dark_mode: bool | None = None
    use_cloud_model: bool = False


__all__ = ["SINGLETON_ID", "ApplicationSettings"]
