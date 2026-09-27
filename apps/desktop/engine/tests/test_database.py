from __future__ import annotations

import typing

import sqlalchemy as sa
from sqlalchemy.exc import OperationalError
from sqlmodel import Session, SQLModel, create_engine, select

from engine.database import db
from engine.models.sql.enteral_formula import EnteralFormula
from engine.models.sql.person import Person

if typing.TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_initialize_database_is_safe_to_call_twice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Startup calls it on every run, so seeding has to stay idempotent."""
    engine = create_engine("sqlite://")
    monkeypatch.setattr(db, "engine", engine)

    db.initialize_database()
    db.initialize_database()

    with Session(engine) as session:
        assert len(session.exec(select(EnteralFormula)).all()) > 0


def test_initialize_database_retries_a_parallel_create_all_race(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine("sqlite://")
    monkeypatch.setattr(db, "engine", engine)
    real_create_all = SQLModel.metadata.create_all
    calls = 0

    def racing_create_all(bind) -> None:  # noqa: ANN001
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OperationalError(
                "CREATE TABLE enteral_formula",
                {},
                Exception("table enteral_formula already exists"),
            )
        real_create_all(bind)

    monkeypatch.setattr(SQLModel.metadata, "create_all", racing_create_all)

    db.initialize_database()

    assert calls == 2  # noqa: PLR2004
    assert "settings" in sa.inspect(engine).get_table_names()


def test_initialize_database_creates_the_person_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine("sqlite://")
    monkeypatch.setattr(db, "engine", engine)

    db.initialize_database()

    tables = set(sa.inspect(engine).get_table_names())
    assert {
        "person",
        "document",
        "clinical_source",
        "clinical_fact",
        "ncp_note",
        "ncp_note_embedding",
        "settings",
    } <= tables
    assert "person_weight" not in tables
    assert "person_clinical_note" not in tables
    assert "clinical_source_embedding" not in tables
    assert tables == set(SQLModel.metadata.tables)


def test_ingested_person_data_persists_to_the_sqlite_file(tmp_path: Path) -> None:
    database_path = tmp_path / "facts.db"
    engine = create_engine(f"sqlite:///{database_path}")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Person(name="Doe, Jane"))
        session.commit()
    engine.dispose()

    reopened = create_engine(f"sqlite:///{database_path}")
    with Session(reopened) as session:
        assert [person.name for person in session.exec(select(Person)).all()] == [
            "Doe, Jane",
        ]
