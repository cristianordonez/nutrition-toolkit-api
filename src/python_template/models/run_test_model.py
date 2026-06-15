"""Base Model will be pydantic class that grabs default values from environment or config.ini"""

from __future__ import annotations

from pydantic import (
    Field,
    PostgresDsn,
)

from .base import AppSettings


class RunTestModel(AppSettings):
    auth_key: str = Field(description="Authentication key")
    api_key: str = Field(description="API key")
    pg_dsn: PostgresDsn = Field(
        description="PostgreSQL DSN",
        examples=["postgres://user:pass@localhost:5432/foobar"],
    )
