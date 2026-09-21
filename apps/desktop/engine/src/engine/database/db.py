"""Local SQLite database engine for the desktop app.

``facts.db`` is the device's system of record for every person and clinical
record ingested here. ``SETTINGS`` also declares ``settings_database_path``
for app settings/preferences, but no tables are assigned to it yet, so only
the facts database is wired up.

Schema is bootstrapped with ``create_all``, which adds missing tables but
never alters existing ones. That is enough for a fresh install; changing a
model on an already-populated device needs migration tooling engine does not
have yet.
"""

from __future__ import annotations

import typing

from sqlmodel import Session, SQLModel, create_engine

from engine.models import sql  # noqa: F401 - registers every table on the metadata
from engine.models.settings import SETTINGS
from engine.repositories.facility_repo import FacilityRepo

if typing.TYPE_CHECKING:
    from collections.abc import Generator


_FACTS_DATABASE_PATH = SETTINGS.facts_database_path.expanduser()
_FACTS_DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    f"sqlite:///{_FACTS_DATABASE_PATH}",
    echo=False,
)


def get_session() -> Generator[Session, None, None]:
    """Generate database session."""
    with Session(engine, expire_on_commit=False) as session:
        yield session


def initialize_database() -> None:
    """Create any missing tables, then seed built-in data.

    Safe to call on every startup: ``create_all`` skips tables that already
    exist and seeding is idempotent.
    """
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        FacilityRepo(session).seed_defaults()
