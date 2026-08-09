from __future__ import annotations

import importlib
import sys
import typing

from pydantic import PostgresDsn

if typing.TYPE_CHECKING:
    from pathlib import Path
    from types import ModuleType

    import pytest

DEFAULT_PORT = 8000
DEFAULT_POOL_SIZE = 50
DEFAULT_MAX_OVERFLOW = 100


def _reload_settings_module() -> ModuleType:
    sys.modules.pop("ntk.models.settings", None)
    sys.modules.pop("ntk.models.base", None)
    return importlib.import_module("ntk.models.settings")


def test_settings_loads_environment_variables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_port = 5433
    monkeypatch.setenv("NTK_PORT", value="8000")
    monkeypatch.setenv("DATABASE_USER", "user")
    monkeypatch.setenv("DATABASE_HOST", "localhost")
    monkeypatch.setenv("DATABASE_NAME", "db")
    monkeypatch.setenv("DATABASE_PASSWORD", "pass")
    monkeypatch.setenv("DATABASE_PORT", f"{database_port}")
    settings_module = _reload_settings_module()
    settings = settings_module.Settings()
    assert settings.port == DEFAULT_PORT
    assert settings.database_user == "user"
    assert settings.database_host == "localhost"
    assert settings.database_name == "db"
    assert settings.database_password == "pass"  # noqa: S105
    assert settings.database_port == database_port
    assert settings.pool_size == DEFAULT_POOL_SIZE
    assert settings.max_overflow == DEFAULT_MAX_OVERFLOW
    assert isinstance(settings.database_url, PostgresDsn)
    assert (
        str(settings.database_url) == "postgresql+psycopg://user:pass@localhost:5433/db"
    )


def test_settings_uses_env_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    default_port = 5432
    env_file = tmp_path / ".env"
    env_file.write_text(
        f"NTK_PORT=8000\nDATABASE_USER=user\nDATABASE_HOST=localhost\nDATABASE_NAME=db\nDATABASE_PASSWORD=pass\nDATABASE_PORT={default_port}",
    )
    monkeypatch.setenv("NTK_CONFIG_FILE", str(env_file))
    for key in [
        "NTK_PORT",
        "DATABASE_USER",
        "DATABASE_HOST",
        "DATABASE_NAME",
        "DATABASE_PASSWORD",
        "DATABASE_PORT",
    ]:
        monkeypatch.delenv(key, raising=False)
    settings_module = _reload_settings_module()
    settings = settings_module.Settings()
    assert settings.port == DEFAULT_PORT
    assert settings.database_user == "user"
    assert settings.database_host == "localhost"
    assert settings.database_name == "db"
    assert settings.database_password == "pass"  # noqa: S105
    assert settings.database_port == default_port
