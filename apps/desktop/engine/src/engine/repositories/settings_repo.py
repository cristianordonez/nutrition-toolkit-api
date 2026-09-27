"""Persistence operations for singleton application settings."""

from __future__ import annotations

import typing

from sqlmodel import select

from engine.models.sql.settings import SINGLETON_ID, ApplicationSettings

if typing.TYPE_CHECKING:
    from sqlmodel import Session


class SettingsRepo:
    """Read and write settings through the application's shared session."""

    def __init__(self, session: Session) -> None:
        """Bind the repository to an existing unit-of-work session."""
        self.session = session

    def get(self) -> ApplicationSettings:
        """Return the singleton settings row, creating its defaults if absent."""
        stored = self.session.exec(select(ApplicationSettings)).first()
        if stored is not None:
            return stored
        created = ApplicationSettings(id=SINGLETON_ID)
        self.session.add(created)
        self.session.commit()
        self.session.refresh(created)
        return created

    def save(self, settings: ApplicationSettings) -> ApplicationSettings:
        """Persist and return the singleton settings row."""
        settings.id = SINGLETON_ID
        self.session.add(settings)
        self.session.commit()
        self.session.refresh(settings)
        return settings

    def update(self, **changes: object) -> ApplicationSettings:
        """Validate and persist a partial settings update."""
        stored = self.get()
        unknown = set(changes) - set(ApplicationSettings.model_fields)
        if unknown:
            msg = f"Unknown application settings: {', '.join(sorted(unknown))}"
            raise ValueError(msg)
        for field_name, value in changes.items():
            setattr(stored, field_name, value)
        return self.save(stored)


__all__ = ["SettingsRepo"]
