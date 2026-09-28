"""Persistent application preferences in the main SQLite database."""

from __future__ import annotations

from sqlalchemy import CheckConstraint, Column, Enum
from sqlmodel import Field, SQLModel

from engine.models.ai import AIProvider

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
    #: Where inference runs. Changing it is always the user's explicit choice;
    #: a failing provider never switches to another on its own.
    ai_provider: AIProvider = Field(
        default=AIProvider.LOCAL,
        sa_column=Column(
            Enum(
                AIProvider,
                name="ai_provider",
                values_callable=lambda enum_type: [item.value for item in enum_type],
            ),
            nullable=False,
            default=AIProvider.LOCAL.value,
        ),
    )


__all__ = ["SINGLETON_ID", "ApplicationSettings"]
