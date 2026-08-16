from __future__ import annotations

import typing

from pydantic import PostgresDsn

from ntk.models.settings import Settings

if typing.TYPE_CHECKING:
    from pathlib import Path

    import pytest

DEFAULT_PORT = 8000
DEFAULT_DATABASE_URL = (
    "postgresql+psycopg://admin:pw@test.database.us-east-2:5432/nutrition-toolkit"
)


def test_settings_loads_environment_variables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NTK_PORT", value="8000")
    monkeypatch.setenv(
        "NTK_DATABASE_URL",
        DEFAULT_DATABASE_URL,
    )
    settings = Settings()
    assert settings.database_url == PostgresDsn(DEFAULT_DATABASE_URL)
    assert settings.port == DEFAULT_PORT


def test_settings_uses_env_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        f"NTK_PORT=8000\nNTK_DATABASE_URL={DEFAULT_DATABASE_URL}",
    )
    monkeypatch.setenv("NTK_CONFIG_FILE", str(env_file))
    for key in [
        "NTK_PORT",
    ]:
        monkeypatch.delenv(key, raising=False)
    settings = Settings()
    assert settings.port == DEFAULT_PORT
