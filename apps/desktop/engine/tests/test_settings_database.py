from __future__ import annotations

import typing

from sqlmodel import Session, SQLModel, create_engine, select

import engine.models.sql  # noqa: F401
from engine.models.sql.settings import SINGLETON_ID, ApplicationSettings
from engine.repositories.settings_repo import SettingsRepo

if typing.TYPE_CHECKING:
    from pathlib import Path


def test_settings_share_the_application_metadata() -> None:
    assert "settings" in SQLModel.metadata.tables
    assert "person" in SQLModel.metadata.tables


def test_one_database_contains_settings_and_clinical_tables() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        rows = [SettingsRepo(session).get()]
    assert len(rows) == 1
    assert rows[0].id == SINGLETON_ID


def test_user_settings_round_trip_in_the_application_database(tmp_path: Path) -> None:
    database_path = tmp_path / "facts.db"
    engine = create_engine(f"sqlite:///{database_path}")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        stored = SettingsRepo(session).get()
        stored.full_name = "Jane Doe"
        stored.credentials = "RD, LDN"
        SettingsRepo(session).save(stored)
    engine.dispose()

    reopened = create_engine(f"sqlite:///{database_path}")
    with Session(reopened) as session:
        settings = SettingsRepo(session).get()
        assert settings.full_name == "Jane Doe"
        assert settings.credentials == "RD, LDN"


def test_saving_twice_keeps_exactly_one_row(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'facts.db'}")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        repository = SettingsRepo(session)
        first = repository.get()
        first.full_name = "First"
        repository.save(first)
        second = repository.get()
        second.full_name = "Second"
        repository.save(second)

        rows = session.exec(select(ApplicationSettings)).all()

    assert [row.full_name for row in rows] == ["Second"]
