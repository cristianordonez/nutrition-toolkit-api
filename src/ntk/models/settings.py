from __future__ import annotations

from pydantic import Field, PostgresDsn, computed_field

from .base import CustomBaseSettings


class Settings(CustomBaseSettings):
    """Initial application settings."""

    ntk_api_key: str
    database_user: str
    database_host: str
    database_name: str
    database_password: str
    database_port: int = Field(default=5432)
    pool_size: int = Field(default=50)
    max_overflow: int = Field(default=100)

    @computed_field
    @property
    def database_url(self) -> PostgresDsn:
        """Validates postgres connection string and connection."""
        return PostgresDsn(
            f"postgresql+psycopg://{self.database_user}:"
            f"{self.database_password}@{self.database_host}:"
            f"{self.database_port}/{self.database_name}",
        )


settings = Settings()  # ty: ignore[missing-argument]
