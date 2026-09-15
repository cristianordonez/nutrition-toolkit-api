from __future__ import annotations

from pathlib import Path

from pydantic import Field, HttpUrl

from ntk.models.base import CustomBaseSettings
from ntk.utils.parallel import PoolMode


class Settings(CustomBaseSettings):
    """Desktop engine settings. Pulls default values from the environment.

    Default path for .env file to source from comes from NTK_CONFIG_FILE env variable.
    """

    facts_database_path: Path = Field(
        default=Path("~/.nutrition-toolkit/facts.db"),
        description="Local SQLite database holding extracted person/clinical data.",
    )
    settings_database_path: Path = Field(
        default=Path("~/.nutrition-toolkit/settings.db"),
        description="Local SQLite database holding app settings/preferences.",
    )
    local_model_path: Path | None = Field(
        default=None,
        description="Path to a downloaded on-device model (seam for a future "
        "llama.cpp-backed extraction agent; unused while extraction runs on OpenAI).",
    )
    open_ai_api_key: str = Field(description="API key to access the OpenAI API")
    debug: bool = Field(description="Enable debug logging.", default=False)
    document_ingestion_pool_mode: PoolMode = Field(default=PoolMode.THREAD)
    document_ingestion_workers: int = Field(default=3, ge=1)
    clinical_note_extraction_concurrency: int = Field(default=8, ge=1)
    cloud_api_base_url: HttpUrl = Field(
        default=HttpUrl("http://localhost:8000"),
        description="Base URL of the cloud-api instance used for NCP generation.",
    )


SETTINGS = Settings()
