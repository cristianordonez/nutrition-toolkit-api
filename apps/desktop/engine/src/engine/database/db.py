"""SQLite connections for the desktop engine; schema lives in migrations."""

from __future__ import annotations

import sqlite3
import time
import typing

import sqlite_vec
from sqlalchemy import URL, event
from sqlmodel import create_engine

from engine.models.settings import SETTINGS

if typing.TYPE_CHECKING:
    from sqlalchemy import Engine


def configure_connection(
    dbapi_connection: sqlite3.Connection,
    _record: object,
) -> None:
    """Enable foreign keys, wait for concurrent writers, and load sqlite-vec."""
    dbapi_connection.execute("PRAGMA foreign_keys = ON")
    dbapi_connection.execute("PRAGMA busy_timeout = 30000")
    _enable_wal(dbapi_connection)
    dbapi_connection.enable_load_extension(True)  # noqa: FBT003
    try:
        sqlite_vec.load(dbapi_connection)
    finally:
        dbapi_connection.enable_load_extension(False)  # noqa: FBT003


def _enable_wal(connection: sqlite3.Connection) -> None:
    """Retry the journal-mode race that SQLite's busy timeout does not wait for."""
    deadline = time.monotonic() + 30
    while True:
        try:
            connection.execute("PRAGMA journal_mode = WAL")
        except sqlite3.OperationalError as error:  # noqa: PERF203 - bounded lock retry
            if (
                error.sqlite_errorcode
                not in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}
                or time.monotonic() >= deadline
            ):
                raise
            time.sleep(0.05)
        else:
            return


def create_database_engine(url: str | URL) -> Engine:
    """Create a SQLite engine with the same configuration as the application."""
    database = create_engine(url, echo=False)
    event.listen(database, "connect", configure_connection)
    return database


def database_url() -> URL:
    """Resolve the configured database file, creating its parent if necessary."""
    path = SETTINGS.database_path.expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    return URL.create("sqlite", database=str(path))


engine = create_database_engine(database_url())
