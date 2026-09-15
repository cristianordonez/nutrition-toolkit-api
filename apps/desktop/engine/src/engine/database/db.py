"""Local SQLite database engine for the desktop app.

This deliberately does not yet wire up the two separate SQLite databases
described in the split refactor plan (facts vs. settings) -- ``SETTINGS``
already declares both paths, but bootstrapping/migrations for them are
future work. For now this provides one inert, importable engine so the rest
of the app (repositories, controllers) can be exercised.
"""

from __future__ import annotations

import typing

from sqlmodel import Session, create_engine

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
    """Seed built-in data after schema creation.

    This function intentionally does not create or alter tables -- real
    dual-database bootstrapping/migrations are future work.
    """
    with Session(engine) as session:
        FacilityRepo(session).seed_defaults()
