from __future__ import annotations

import typing

import sqlalchemy as sa
from sqlmodel import Session, SQLModel, create_engine, select

from engine.database import settings_db
from engine.models.user_settings import SINGLETON_ID, SettingsBase, UserSettings
from engine.repositories.user_settings_repo import UserSettingsRepo

if typing.TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_settings_tables_are_not_in_the_facts_metadata() -> None:
    assert "user_settings" in SettingsBase.metadata.tables
    assert "user_settings" not in SQLModel.metadata.tables
    assert "person" in SQLModel.metadata.tables
    assert "person" not in SettingsBase.metadata.tables


def test_initialize_settings_database_creates_only_settings_tables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine("sqlite://")
    monkeypatch.setattr(settings_db, "settings_engine", engine)

    settings_db.initialize_settings_database()
    settings_db.initialize_settings_database()

    assert sa.inspect(engine).get_table_names() == ["user_settings"]
    with Session(engine) as session:
        rows = session.exec(select(UserSettings)).all()
    assert len(rows) == 1
    assert rows[0].id == SINGLETON_ID


def test_user_settings_round_trip_to_their_own_file(tmp_path: Path) -> None:
    database_path = tmp_path / "settings.db"
    engine = create_engine(f"sqlite:///{database_path}")
    SettingsBase.metadata.create_all(engine)

    with Session(engine) as session:
        stored = UserSettingsRepo(session).get()
        stored.full_name = "Jane Doe"
        stored.credentials = "RD, LDN"
        stored.default_facility_identifier = "embassy-manor-edison"
        UserSettingsRepo(session).save(stored)
    engine.dispose()

    reopened = create_engine(f"sqlite:///{database_path}")
    with Session(reopened) as session:
        settings = UserSettingsRepo(session).get()
        assert settings.full_name == "Jane Doe"
        assert settings.credentials == "RD, LDN"
        assert settings.default_facility_identifier == "embassy-manor-edison"


def test_saving_twice_keeps_exactly_one_row(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'settings.db'}")
    SettingsBase.metadata.create_all(engine)

    with Session(engine) as session:
        repository = UserSettingsRepo(session)
        first = repository.get()
        first.full_name = "First"
        repository.save(first)
        second = repository.get()
        second.full_name = "Second"
        repository.save(second)

        rows = session.exec(select(UserSettings)).all()

    assert [row.full_name for row in rows] == ["Second"]
