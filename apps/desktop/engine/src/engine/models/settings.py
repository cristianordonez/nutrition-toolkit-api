# Pydantic resolves these annotation types at runtime when building schemas.
# ruff: noqa: TC003

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import SettingsConfigDict

from engine.models.base import CustomBaseSettings
from engine.paths import data_dir, log_dir


class Settings(CustomBaseSettings):
    """Desktop engine settings. Pulls default values from the environment.

    Default path for .env file to source from comes from NTK_CONFIG_FILE env variable.
    """

    database_path: Path = Field(
        default_factory=lambda: data_dir() / "facts.db",
        description="Local SQLite database holding clinical data and app settings.",
    )
    log_file: Path | None = Field(
        default_factory=lambda: log_dir() / "engine.log",
        description="Where the engine writes its log. Set empty to log only to "
        "the console.",
    )
    debug: bool = Field(description="Enable debug logging.", default=False)
    clinical_note_extraction_concurrency: int = Field(default=8, ge=1)


class LocalAISettings(CustomBaseSettings):
    """Where Local AI's llama.cpp server is, read from ``NUTRITION_AI_*``.

    The engine only ever talks to a URL. It does not start, stop, locate or
    configure llama-server: in development you run it yourself (see
    ``docs/local-ai.md``); in a packaged app the desktop runtime will.
    """

    model_config = SettingsConfigDict(env_prefix="nutrition_ai_")

    llama_url: str = Field(
        default="http://127.0.0.1:8080",
        description="Base URL of the llama.cpp server. Must be on this machine.",
    )
    llama_api_key: str | None = Field(
        default=None,
        description="API key the server was started with (--api-key), if any.",
    )
    temperature: float | None = Field(default=None, ge=0)
    max_tokens: int | None = Field(default=None, ge=1)
    request_timeout_seconds: float = Field(default=600, gt=0)


SETTINGS = Settings()
LOCAL_AI_SETTINGS = LocalAISettings()
