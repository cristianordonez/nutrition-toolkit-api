"""Exercise real packaged migrations, startup races, and schema rollback."""

from __future__ import annotations

import io
import os
import subprocess
import sys
import typing
from concurrent.futures import ThreadPoolExecutor

import pytest
import sqlalchemy as sa
from alembic import command
from sqlmodel import Session, SQLModel, select

from engine.database import bootstrap, sessions
from engine.database.db import create_database_engine
from engine.models.ncp_note import NCPNoteStatus, NCPNoteType
from engine.models.sql.enteral_formula import EnteralFormula
from engine.models.sql.ncp_note import NCPNote
from engine.models.sql.person import Person
from engine.models.sql.settings import ApplicationSettings

if typing.TYPE_CHECKING:
    from pathlib import Path

    from alembic.config import Config


def test_initialize_database_is_safe_to_call_twice() -> None:
    database = create_database_engine("sqlite://")
    bootstrap.initialize_database(database)
    bootstrap.initialize_database(database)

    with Session(database) as session:
        assert session.exec(select(EnteralFormula)).all()
        assert len(session.exec(select(ApplicationSettings)).all()) == 1
    with database.connect() as connection:
        assert (
            connection.exec_driver_sql(
                "SELECT version_num FROM alembic_version",
            ).scalar_one()
            == "0004"
        )
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
        assert connection.exec_driver_sql("SELECT vec_version()").scalar_one()


def test_migrations_match_relational_metadata_and_ignore_vector_shadow_tables() -> None:
    database = create_database_engine("sqlite://")
    bootstrap.upgrade_database(database)

    tables = set(sa.inspect(database).get_table_names())
    assert set(SQLModel.metadata.tables) <= tables
    assert {"knowledge_chunk_vector", "ncp_note_vector", "alembic_version"} <= tables
    assert "ncp_note_embedding" not in tables
    assert "knowledge_chunk_embedding" not in tables
    with database.connect() as connection:
        config = bootstrap.migration_config()
        config.attributes["connection"] = connection
        command.check(config)


def test_initial_and_vector_revisions_upgrade_and_downgrade_separately() -> None:
    database = create_database_engine("sqlite://")
    config = bootstrap.migration_config()
    with database.connect() as connection:
        config.attributes["connection"] = connection
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        command.upgrade(config, "0001")
        connection.commit()
    assert set(sa.inspect(database).get_table_names()) == {
        *SQLModel.metadata.tables,
        "alembic_version",
    }

    with Session(database) as session:
        session.add(Person(name="Persistent person"))
        session.commit()
    bootstrap.upgrade_database(database)

    with database.connect() as connection:
        config.attributes["connection"] = connection
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        command.downgrade(config, "0001")
        connection.commit()
    assert "ncp_note_vector" not in sa.inspect(database).get_table_names()
    with Session(database) as session:
        assert session.exec(select(Person)).one().name == "Persistent person"
    bootstrap.upgrade_database(database)
    with database.connect() as connection:
        config.attributes["connection"] = connection
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        command.downgrade(config, "base")
        connection.commit()
    assert sa.inspect(database).get_table_names() == ["alembic_version"]


def test_failed_migration_rolls_back_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = create_database_engine("sqlite://")

    def fail_after_ddl(config: Config, _revision: str) -> None:
        connection = config.attributes["connection"]
        connection.exec_driver_sql("CREATE TABLE partial_schema (id INTEGER)")
        msg = "failed revision"
        raise RuntimeError(msg)

    with monkeypatch.context() as patch:
        patch.setattr(bootstrap.command, "upgrade", fail_after_ddl)
        with pytest.raises(RuntimeError, match="failed revision"):
            bootstrap.upgrade_database(database)
    assert sa.inspect(database).get_table_names() == []
    bootstrap.upgrade_database(database)


def test_unversioned_database_is_left_untouched() -> None:
    database = create_database_engine("sqlite://")
    with database.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE legacy_data (value TEXT)")
        connection.exec_driver_sql("INSERT INTO legacy_data VALUES ('keep me')")
    with pytest.raises(RuntimeError, match="predates Alembic"):
        bootstrap.initialize_database(database)
    with database.connect() as connection:
        assert (
            connection.exec_driver_sql("SELECT value FROM legacy_data").scalar_one()
            == "keep me"
        )
    assert sa.inspect(database).get_table_names() == ["legacy_data"]


def test_offline_upgrade_contains_both_schemas() -> None:
    config = bootstrap.migration_config()
    output = io.StringIO()
    config.output_buffer = output
    command.upgrade(config, "head", sql=True)
    sql = output.getvalue()
    assert "CREATE TABLE person" in sql
    assert "CREATE VIRTUAL TABLE knowledge_chunk_vector USING vec0" in sql
    assert "CREATE VIRTUAL TABLE ncp_note_vector USING vec0" in sql
    assert "FLOAT[384] distance_metric=cosine" in sql


def test_parallel_processes_initialize_one_database(tmp_path: Path) -> None:
    database_path = tmp_path / "facts.db"
    env = {**os.environ, "NTK_DATABASE_PATH": str(database_path)}

    def run_startup(_index: int) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "from engine.database.bootstrap import initialize_database; "
                    "initialize_database()"
                ),
            ],
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=45,
        )

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(run_startup, range(4)))
    for result in results:
        assert result.returncode == 0, result.stderr
        assert result.stdout == ""
    database = create_database_engine(f"sqlite:///{database_path}")
    with Session(database) as session:
        assert session.exec(select(EnteralFormula)).all()
        assert len(session.exec(select(ApplicationSettings)).all()) == 1
    database.dispose()


def test_ingested_person_data_persists_to_the_sqlite_file(tmp_path: Path) -> None:
    database_path = tmp_path / "facts.db"
    database = create_database_engine(f"sqlite:///{database_path}")
    bootstrap.initialize_database(database)
    with Session(database) as session:
        session.add(Person(name="Doe, Jane"))
        session.commit()
    database.dispose()

    reopened = create_database_engine(f"sqlite:///{database_path}")
    bootstrap.initialize_database(reopened)
    with Session(reopened) as session:
        assert [person.name for person in session.exec(select(Person)).all()] == [
            "Doe, Jane",
        ]
    reopened.dispose()


def test_shared_sessions_preserve_caller_ownership(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = create_database_engine("sqlite://")
    bootstrap.upgrade_database(database)
    monkeypatch.setattr(sessions, "engine", database)
    with sessions.controller_session() as owned:
        with sessions.settings_session(owned) as reused:
            assert reused is owned
        owned.add(Person(name="Session user"))
        owned.commit()
        assert owned.exec(select(Person)).one().name == "Session user"


def _reference_database(path: Path) -> Path:
    """A small stand-in for the bundled starter database: one NCP example."""
    database = create_database_engine(f"sqlite:///{path}")
    bootstrap.upgrade_database(database)
    with Session(database) as session:
        session.add(
            NCPNote(
                note_type=NCPNoteType.QUARTERLY,
                content="Quarterly review.",
                status=NCPNoteStatus.EXAMPLE,
            ),
        )
        session.commit()
    database.dispose()
    return path


def _example_contents(path: Path) -> list[str]:
    database = create_database_engine(f"sqlite:///{path}")
    with Session(database) as session:
        contents = [note.content for note in session.exec(select(NCPNote)).all()]
    database.dispose()
    return contents


def test_missing_database_is_installed_from_reference(tmp_path: Path) -> None:
    reference = _reference_database(tmp_path / "reference.db")
    target = tmp_path / "data" / "facts.db"

    assert bootstrap.install_reference_database(target, reference) is True
    assert _example_contents(target) == ["Quarterly review."]
    assert [path.name for path in target.parent.iterdir()] == ["facts.db"]


def test_existing_database_is_never_replaced_by_reference(tmp_path: Path) -> None:
    reference = _reference_database(tmp_path / "reference.db")
    target = tmp_path / "facts.db"
    target.write_bytes(b"the user's database")

    assert bootstrap.install_reference_database(target, reference) is False
    assert target.read_bytes() == b"the user's database"


def test_no_bundled_reference_leaves_database_to_be_created(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(bootstrap, "bundled_reference_database", lambda: None)
    target = tmp_path / "facts.db"

    assert bootstrap.install_reference_database(target) is False
    assert not target.exists()


def test_application_database_starts_from_reference_and_is_seeded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reference = _reference_database(tmp_path / "reference.db")
    target = tmp_path / "facts.db"
    application = create_database_engine(f"sqlite:///{target}")
    monkeypatch.setattr(bootstrap, "engine", application)
    monkeypatch.setattr(bootstrap, "bundled_reference_database", lambda: reference)

    bootstrap.initialize_database()

    with Session(application) as session:
        assert [note.content for note in session.exec(select(NCPNote)).all()] == [
            "Quarterly review.",
        ]
        assert len(session.exec(select(ApplicationSettings)).all()) == 1
    application.dispose()


def test_explicit_database_is_not_installed_from_reference(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reference = _reference_database(tmp_path / "reference.db")
    monkeypatch.setattr(bootstrap, "bundled_reference_database", lambda: reference)
    target = tmp_path / "facts.db"
    database = create_database_engine(f"sqlite:///{target}")

    bootstrap.initialize_database(database)
    database.dispose()

    assert _example_contents(target) == []


def test_a_stored_ollama_choice_becomes_local_ai() -> None:
    database = create_database_engine("sqlite://")
    with database.connect() as connection:
        config = bootstrap.migration_config()
        config.attributes["connection"] = connection
        command.upgrade(config, "0003")
        connection.exec_driver_sql(
            "INSERT INTO settings (id, ai_provider) VALUES (1, 'ollama')",
        )
        connection.commit()
        command.upgrade(config, "head")
        connection.commit()

        assert (
            connection.exec_driver_sql("SELECT ai_provider FROM settings").scalar_one()
            == "local"
        )
