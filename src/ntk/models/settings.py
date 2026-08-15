from __future__ import annotations

from pydantic import Field, PostgresDsn

from .base import CustomBaseSettings


class Settings(CustomBaseSettings):
    """Initial application settings. Pulls default values from the environment.

    Default path for .env file to source from comes from NTK_CONFIG_FILE env variable.
    """

    database_url: PostgresDsn = Field(
        description="Full postgres connection string. Example: 'postgresql+psycopg://{user}{pw}@{host}:{port}/{name}",
    )
    pool_size: int = Field(default=50)
    max_overflow: int = Field(default=100)
    port: int = Field(description="Port that FastAPI server will run on.", default=8000)
    debug: bool = Field(description="Enable debug logging.")


def get_settings() -> Settings:
    """Return a settings instance using the current environment."""
    return Settings()
