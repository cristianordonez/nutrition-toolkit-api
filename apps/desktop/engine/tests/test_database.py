from __future__ import annotations

import typing

import sqlalchemy as sa
from sqlmodel import Session, SQLModel, create_engine, select

from engine.database import db
from engine.defaults import DEFAULT_FACILITIES
from engine.models.sql.facility import Facility
from engine.models.sql.person import Person

if typing.TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_initialize_database_seeds_facilities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine("sqlite://")
    monkeypatch.setattr(db, "engine", engine)

    db.initialize_database()
    db.initialize_database()

    with Session(engine) as session:
        assert len(session.exec(select(Facility)).all()) == len(DEFAULT_FACILITIES)


def test_initialize_database_creates_the_person_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine("sqlite://")
    monkeypatch.setattr(db, "engine", engine)

    db.initialize_database()

    tables = set(sa.inspect(engine).get_table_names())
    assert {"person", "person_weight", "person_clinical_note", "document"} <= tables
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
