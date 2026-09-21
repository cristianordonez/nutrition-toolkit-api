"""Local SQLite database holding the device user's own settings.

Deliberately a separate file and a separate engine from ``facts.db`` (see
``engine.database.db``). The clinical record and the user's own profile have
different lifetimes: clearing, restoring, or re-ingesting clinical data should
not disturb who the user is, and the two carry different privacy weight.

Because ``UserSettings`` is registered on its own metadata, ``create_all``
here can only build settings tables, and ``create_all`` against the facts
database can only build clinical tables.
"""

from __future__ import annotations

import typing

from sqlmodel import Session, create_engine

from engine.models.settings import SETTINGS
from engine.models.user_settings import SettingsBase
from engine.repositories.user_settings_repo import UserSettingsRepo

if typing.TYPE_CHECKING:
    from collections.abc import Generator


_SETTINGS_DATABASE_PATH = SETTINGS.settings_database_path.expanduser()
_SETTINGS_DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

settings_engine = create_engine(
    f"sqlite:///{_SETTINGS_DATABASE_PATH}",
    echo=False,
)


def get_settings_session() -> Generator[Session, None, None]:
    """Generate a settings-database session."""
    with Session(settings_engine, expire_on_commit=False) as session:
        yield session


def initialize_settings_database() -> None:
    """Create any missing settings tables, then ensure the settings row exists.

    Safe to call on every startup: ``create_all`` skips existing tables and
    the row is only created when absent.
    """
    SettingsBase.metadata.create_all(settings_engine)
    with Session(settings_engine) as session:
        UserSettingsRepo(session).get()
