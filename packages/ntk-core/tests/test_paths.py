from __future__ import annotations

import typing

import pytest

from ntk import paths

if typing.TYPE_CHECKING:
    import pathlib


@pytest.fixture
def relocated(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
) -> typing.Callable[[], tuple[pathlib.Path, pathlib.Path]]:
    """Point both the legacy and data directories inside tmp_path."""
    legacy = tmp_path / "legacy"
    data = tmp_path / "data"
    monkeypatch.setattr(paths, "LEGACY_DIR", legacy)
    monkeypatch.setattr(paths, "data_dir", lambda: data)
    return lambda: (legacy, data)


def test_directories_are_distinct_and_absolute() -> None:
    for directory in (paths.data_dir(), paths.log_dir(), paths.config_dir()):
        assert directory.is_absolute()
    # Logs are separate from data so clearing one cannot take the other.
    assert paths.log_dir() != paths.data_dir()
    assert paths.APP_NAME in str(paths.data_dir())


def test_migration_is_a_no_op_without_a_legacy_directory(
    relocated: typing.Callable[[], tuple[pathlib.Path, pathlib.Path]],
) -> None:
    _legacy, _data = relocated()
    assert paths.migrate_legacy_data() == []


def test_migration_moves_databases_and_removes_the_old_directory(
    relocated: typing.Callable[[], tuple[pathlib.Path, pathlib.Path]],
) -> None:
    legacy, data = relocated()
    legacy.mkdir()
    (legacy / "facts.db").write_bytes(b"resident records")
    (legacy / "settings.db").write_bytes(b"profile")

    moved = paths.migrate_legacy_data()

    assert sorted(moved) == ["facts.db", "settings.db"]
    assert (data / "facts.db").read_bytes() == b"resident records"
    assert (data / "settings.db").read_bytes() == b"profile"
    assert not legacy.exists()


def test_migration_never_overwrites_an_existing_database(
    relocated: typing.Callable[[], tuple[pathlib.Path, pathlib.Path]],
) -> None:
    legacy, data = relocated()
    legacy.mkdir()
    (legacy / "facts.db").write_bytes(b"stale")
    data.mkdir(parents=True)
    (data / "facts.db").write_bytes(b"current records")

    moved = paths.migrate_legacy_data()

    # The database in use wins, and the old file is left where it was rather
    # than silently destroyed.
    assert moved == []
    assert (data / "facts.db").read_bytes() == b"current records"
    assert (legacy / "facts.db").read_bytes() == b"stale"
    assert legacy.exists()
