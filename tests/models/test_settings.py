from __future__ import annotations

import typing

from pydantic import PostgresDsn

from ntk.models.settings import Settings
from ntk.utils.parallel import PoolMode

if typing.TYPE_CHECKING:
    from pathlib import Path

    import pytest

DEFAULT_PORT = 8000
DEFAULT_DATABASE_URL = (
    "postgresql+psycopg://admin:pw@test.database.us-east-2:5432/nutrition-toolkit"
)
TEST_REDIS_DSN = "redis://localhost:6379/0"


def test_document_ingestion_pool_defaults() -> None:
    settings = Settings()

    assert settings.document_ingestion_pool_mode is PoolMode.THREAD
    assert settings.document_ingestion_workers == 3  # noqa: PLR2004
    assert settings.progress_note_extraction_concurrency == 8  # noqa: PLR2004


def test_progress_note_extraction_concurrency_is_configurable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NTK_PROGRESS_NOTE_EXTRACTION_CONCURRENCY", "5")

    assert Settings().progress_note_extraction_concurrency == 5  # noqa: PLR2004


def test_settings_loads_environment_variables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NTK_PORT", value="8000")
    monkeypatch.setenv("NTK_REDIS_DSN", value=TEST_REDIS_DSN)
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
        f"NTK_REDIS_DSN={TEST_REDIS_DSN}\nNTK_PORT=8000\nNTK_DATABASE_URL={DEFAULT_DATABASE_URL}",
    )
    monkeypatch.setenv("NTK_CONFIG_FILE", str(env_file))
    for key in [
        "NTK_PORT",
    ]:
        monkeypatch.delenv(key, raising=False)
    settings = Settings()
    assert settings.port == DEFAULT_PORT
