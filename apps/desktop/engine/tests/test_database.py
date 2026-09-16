from __future__ import annotations

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import OperationalError
from sqlmodel import Session, SQLModel, create_engine, select

from engine.database import db
from engine.defaults import DEFAULT_FACILITIES
from engine.models.sql.facility import Facility


def test_initialize_database_seeds_facilities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine("sqlite://")
    monkeypatch.setattr(db, "engine", engine)
    SQLModel.metadata.create_all(engine)

    db.initialize_database()
    db.initialize_database()

    with Session(engine) as session:
        assert len(session.exec(select(Facility)).all()) == len(DEFAULT_FACILITIES)


def test_initialize_database_does_not_create_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine("sqlite://")
    monkeypatch.setattr(db, "engine", engine)

    with pytest.raises(OperationalError):
        db.initialize_database()

    assert sa.inspect(engine).get_table_names() == []
