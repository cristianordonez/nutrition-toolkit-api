from __future__ import annotations

import pytest
from sqlmodel import Session, SQLModel, create_engine

import engine.models.sql  # noqa: F401
from engine.models.sql.settings import ApplicationSettings
from engine.repositories.settings_repo import SettingsRepo


def _session() -> Session:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def test_dark_mode_starts_unset_so_the_app_follows_the_os() -> None:
    """Defaulting to False would force existing dark-mode users into light."""
    with _session() as session:
        assert SettingsRepo(session).get().dark_mode is None


@pytest.mark.parametrize("value", [True, False, None])
def test_dark_mode_round_trips_each_state(*, value: bool | None) -> None:
    with _session() as session:
        repository = SettingsRepo(session)
        repository.update(dark_mode=value)

        assert repository.get().dark_mode is value


def test_update_leaves_unnamed_fields_alone() -> None:
    """A page that edits one setting must not blank the others."""
    with _session() as session:
        repository = SettingsRepo(session)
        repository.save(
            ApplicationSettings(full_name="Wu, RD", credentials="RD, LDN"),
        )

        repository.update(dark_mode=True)

        stored = repository.get()
        assert stored.full_name == "Wu, RD"
        assert stored.credentials == "RD, LDN"
        assert stored.dark_mode is True


def test_update_rejects_an_unknown_setting() -> None:
    """Typos must fail loudly rather than silently doing nothing."""
    with (
        _session() as session,
        pytest.raises(ValueError, match="Unknown application settings: darkmode"),
    ):
        SettingsRepo(session).update(darkmode=True)
