"""Local SQLite database engine for the desktop app.

The one SQLite file is the device's system of record for resident clinical
data, local reference data, and application preferences.

Schema is bootstrapped with ``create_all``, which adds missing tables but
never alters existing ones. Migrations will be done with alembic.
"""

from __future__ import annotations

import typing

import sqlite_vec
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlmodel import Session, SQLModel, create_engine

from engine.models import sql  # noqa: F401 - registers every table on the metadata
from engine.models.settings import SETTINGS
from engine.repositories.enteral_formula_repo import EnteralFormulaRepo
from engine.repositories.settings_repo import SettingsRepo

if typing.TYPE_CHECKING:
    import sqlite3
    from collections.abc import Generator


# Parallel Tauri commands can collide independently at schema creation,
# reference seeding, and singleton-settings creation. Give each phase room for
# its losing process to observe the winner's commit and retry idempotently.
_INITIALIZATION_ATTEMPTS = 8


_DATABASE_PATH = SETTINGS.database_path.expanduser()
_DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    f"sqlite:///{_DATABASE_PATH}",
    echo=False,
)

print(f"SQLite file located at {_DATABASE_PATH}")  # noqa: T201


@event.listens_for(engine, "connect")
def _configure_connection(
    dbapi_connection: sqlite3.Connection,
    _record: object,
) -> None:
    """Apply pragmas and load sqlite-vec onto every new connection.

    Both are per-connection, not per-database, so this has to run on each one
    rather than once at startup. sqlite-vec supplies ``vec_distance_cosine``,
    which vector search calls directly on the stored BLOBs; there are no
    ``vec0`` tables. A failure to load it is not swallowed: search has no
    other way to score vectors, and a bundle missing the extension should
    fail where it is visible rather than return no results.
    """
    dbapi_connection.execute("PRAGMA foreign_keys = ON")
    dbapi_connection.execute("PRAGMA busy_timeout = 5000")
    dbapi_connection.execute("PRAGMA journal_mode = WAL")
    dbapi_connection.enable_load_extension(True)  # noqa: FBT003
    try:
        sqlite_vec.load(dbapi_connection)
    finally:
        dbapi_connection.enable_load_extension(False)  # noqa: FBT003


def get_session() -> Generator[Session, None, None]:
    """Generate database session."""
    with Session(engine, expire_on_commit=False) as session:
        yield session


def initialize_database() -> None:
    """Create any missing tables, then seed built-in data.

    Safe to call on every startup: ``create_all`` skips tables that already
    exist and seeding is idempotent.
    """
    for attempt in range(_INITIALIZATION_ATTEMPTS):
        try:
            SQLModel.metadata.create_all(engine)
            with Session(engine) as session:
                EnteralFormulaRepo(session).seed_defaults()
                SettingsRepo(session).get()
            return  # noqa: TRY300 - retry loop exits only after every seed commits
        except (IntegrityError, OperationalError) as error:  # noqa: PERF203
            if (
                attempt == _INITIALIZATION_ATTEMPTS - 1
                or not _is_concurrent_initialization_error(error)
            ):
                raise


def _is_concurrent_initialization_error(
    error: IntegrityError | OperationalError,
) -> bool:
    """Recognize races caused by two desktop commands bootstrapping together."""
    message = str(error).casefold()
    return any(
        marker in message
        for marker in (
            "already exists",
            "unique constraint failed",
            "database is locked",
            "database schema is locked",
        )
    )
