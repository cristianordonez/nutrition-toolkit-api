"""Upgrade the bundled Alembic schema and seed built-in application data."""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
import threading
import typing
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlmodel import Session

from engine.database.db import engine
from engine.paths import bundled_reference_database
from engine.repositories.enteral_formula_repo import EnteralFormulaRepo
from engine.repositories.settings_repo import SettingsRepo

if typing.TYPE_CHECKING:
    from sqlalchemy import Engine

logger = logging.getLogger(__name__)

# Alembic installs process-global environment proxies while running revisions.
_MIGRATION_LOCK = threading.Lock()


def migration_config() -> Config:
    """Locate packaged revisions without depending on a development ini file."""
    config = Config()
    location = Path(__file__).with_name("migrations")
    config.set_main_option("script_location", str(location).replace("%", "%%"))
    return config


def upgrade_database(database: Engine) -> None:
    """Apply all revisions atomically, serializing competing desktop processes."""
    with _MIGRATION_LOCK, database.connect() as connection:
        # Acquire SQLite's writer lock BEFORE Alembic reads alembic_version.
        # The next process then observes this one's committed revision.
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        config = migration_config()
        config.attributes["connection"] = connection
        try:
            command.upgrade(config, "head")
            connection.commit()
        except BaseException:
            connection.rollback()
            raise


def install_reference_database(
    path: Path,
    reference: Path | None = None,
) -> bool:
    """Copy the shipped starter database to ``path`` if nothing is there yet.

    Never overwrites: an existing database is the user's, whatever it holds.
    The copy is staged beside ``path`` and hard-linked into place, which fails
    rather than clobbers when another starting process got there first, so
    concurrent CLI processes cannot open a half-copied file.
    """
    reference = reference if reference is not None else bundled_reference_database()
    if reference is None or path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".seed",
        delete=False,
    ) as staged:
        staged_path = Path(staged.name)
    try:
        shutil.copyfile(reference, staged_path)
        try:
            os.link(staged_path, path)
        except FileExistsError:
            return False
    finally:
        staged_path.unlink(missing_ok=True)
    logger.info("Installed the bundled reference database at %s", path)
    return True


def initialize_database(database: Engine | None = None) -> None:
    """Upgrade schema, then idempotently seed reference data and preferences.

    The application's own database starts from the bundled reference copy when
    it does not exist yet; an explicitly passed engine never does.
    """
    if database is None:
        database = engine
        if database.url.database:
            install_reference_database(Path(database.url.database))
    upgrade_database(database)
    # Repositories commit their own writes. Hold an outer transaction so all
    # seeds share one writer lock even when several CLI processes start at once.
    with database.connect() as connection:
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        with Session(connection, expire_on_commit=False) as session:
            EnteralFormulaRepo(session).seed_defaults()
            SettingsRepo(session).get()
        connection.commit()
