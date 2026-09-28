"""The shipped starter database may only ever hold reference data."""

from __future__ import annotations

import pathlib
import runpy
import sqlite3

import pytest
from sqlmodel import Session

from engine.database.bootstrap import initialize_database
from engine.database.db import create_database_engine
from engine.models.sql.person import Person

_SCRIPT = pathlib.Path(__file__).resolve().parents[1] / (
    "scripts/build_reference_database.py"
)


@pytest.fixture
def build() -> dict[str, object]:
    return runpy.run_path(str(_SCRIPT))


def _database(path: pathlib.Path, *, with_person: bool = False) -> pathlib.Path:
    database = create_database_engine(f"sqlite:///{path}")
    initialize_database(database)
    if with_person:
        with Session(database) as session:
            session.add(Person(name="Doe, Jane"))
            session.commit()
    database.dispose()
    return path


def test_build_drops_user_settings(
    tmp_path: pathlib.Path,
    build: dict[str, object],
) -> None:
    source = _database(tmp_path / "facts.db")
    destination = tmp_path / "reference" / "facts.db"

    build["build"](source, destination)  # ty: ignore[call-non-callable]

    with sqlite3.connect(destination) as connection:
        assert connection.execute("SELECT count(*) FROM settings").fetchone() == (0,)
        assert connection.execute("PRAGMA journal_mode").fetchone() == ("delete",)
        assert connection.execute(
            "SELECT count(*) FROM enteral_formula",
        ).fetchone()[0]


def test_build_refuses_a_database_with_resident_data(
    tmp_path: pathlib.Path,
    build: dict[str, object],
) -> None:
    source = _database(tmp_path / "facts.db", with_person=True)
    destination = tmp_path / "reference" / "facts.db"

    with pytest.raises(RuntimeError, match="person has 1 row"):
        build["build"](source, destination)  # ty: ignore[call-non-callable]
    assert not destination.exists()
