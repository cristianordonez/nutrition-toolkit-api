"""Persistence operations for the device user's own settings."""

from __future__ import annotations

import typing

from sqlmodel import select

from engine.models.user_settings import SINGLETON_ID, UserSettings

if typing.TYPE_CHECKING:
    from sqlmodel import Session


class UserSettingsRepo:
    """Read and write the single user-settings row."""

    def __init__(self, session: Session) -> None:
        """Initialize the repository with a settings-database session."""
        self.session = session

    def get(self) -> UserSettings:
        """Return the user's settings, creating the defaults row when absent."""
        stored = self.session.exec(select(UserSettings)).first()
        if stored is not None:
            return stored
        created = UserSettings(id=SINGLETON_ID)
        self.session.add(created)
        self.session.commit()
        self.session.refresh(created)
        return created

    def save(self, user_settings: UserSettings) -> UserSettings:
        """Persist edits to the settings row."""
        user_settings.id = SINGLETON_ID
        self.session.add(user_settings)
        self.session.commit()
        self.session.refresh(user_settings)
        return user_settings


__all__ = ["UserSettingsRepo"]
