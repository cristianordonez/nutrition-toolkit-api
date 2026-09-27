# Pydantic resolves these annotation types at runtime when building schemas.
# ruff: noqa: TC003

from __future__ import annotations

from pathlib import Path

from pydantic import Field

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
    local_model_path: Path | None = Field(
        default=None,
        description="Path to a downloaded on-device model (seam for a future "
        "llama.cpp-backed extraction agent; unused while extraction runs on OpenAI).",
    )
    use_local_extraction: bool = Field(
        default=False,
        description="Run document extraction on-device via Ollama instead of "
        "OpenAI. Opt-in until local extraction quality is measured against the "
        "hosted model.",
    )
    ollama_host: str = Field(
        default="http://localhost:11434",
        description="Base URL of the local Ollama daemon.",
    )
    ollama_model: str | None = Field(
        default=None,
        description="Override the on-device model. Leave unset to let the app "
        "pick one sized for this machine's memory.",
    )
    open_ai_api_key: str = Field(
        default="",
        description="API key to access the OpenAI API. Optional only when "
        "extraction runs on-device; the hosted path fails at first use without it.",
    )
    debug: bool = Field(description="Enable debug logging.", default=False)
    clinical_note_extraction_concurrency: int = Field(default=8, ge=1)


SETTINGS = Settings()
