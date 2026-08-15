from __future__ import annotations

import base64
import os

from databricks.sdk import WorkspaceClient
from pydantic import Field, PostgresDsn

from .base import CustomBaseSettings

_w = WorkspaceClient()

_SCOPE = os.environ.get("LAKEBASE_SECRET_SCOPE", "database")
_KEY = os.environ.get("LAKEBASE_SECRET_KEY", "ntk-database-url")


def _lakebase_url() -> str:
    """Fetch and decode the Lakebase connection URL from the Databricks secret scope."""
    secret = _w.secrets.get_secret(scope=_SCOPE, key=_KEY)
    return base64.b64decode(secret.value).decode("utf-8")


class Settings(CustomBaseSettings):
    """Initial application settings. Pulls default values from the environment.

    Default path for .env file to source from comes from NTK_CONFIG_FILE env variable.
    """

    database_url: PostgresDsn = Field(
        description="Full postgres connection string. Example: 'postgresql+psycopg://{user}{pw}@{host}:{port}/{name}",
        default=_lakebase_url(),
    )
    pool_size: int = Field(default=50)
    max_overflow: int = Field(default=100)
    port: int = Field(description="Port that FastAPI server will run on.", default=8000)
    debug: bool = Field(description="Enable debug logging.", default=False)


def get_settings() -> Settings:
    """Return a settings instance using the current environment."""
    return Settings()
