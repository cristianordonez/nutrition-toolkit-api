from __future__ import annotations

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import OperationalError
from sqlmodel import Session, SQLModel, create_engine, select

from ntk.database import db
from ntk.defaults import DEFAULT_FACILITIES, DEFAULT_FORMULAS, DEFAULT_PERMISSIONS
from ntk.models.sql.api_key import Permission
from ntk.models.sql.facility import Facility
from ntk.models.sql.food import Food


def test_initialize_database_seeds_permissions_and_formulas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine("sqlite://")
    monkeypatch.setattr(db, "engine", engine)
    SQLModel.metadata.create_all(engine)

    db.initialize_database()
    db.initialize_database()

    with Session(engine) as session:
        assert len(session.exec(select(Food)).all()) == len(DEFAULT_FORMULAS)
        assert len(session.exec(select(Facility)).all()) == len(DEFAULT_FACILITIES)
        permission_names = {
            permission.name for permission in session.exec(select(Permission))
        }
        assert permission_names >= set(DEFAULT_PERMISSIONS)


def test_initialize_database_does_not_create_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine("sqlite://")
    monkeypatch.setattr(db, "engine", engine)

    with pytest.raises(OperationalError):
        db.initialize_database()

    assert sa.inspect(engine).get_table_names() == []
