"""Create a fresh database schema from all registered SQLModel tables."""

# This executable script directory is intentionally not a Python package.

from __future__ import annotations

from sqlalchemy import text
from sqlmodel import SQLModel

# IMPORTANT: import your models so they're registered with SQLModel.metadata
import ntk.models.sql  # noqa: F401
from ntk.database.db import engine


def main() -> None:
    """Create all registered tables that do not already exist."""
    if engine.dialect.name == "postgresql":
        with engine.begin() as connection:
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    SQLModel.metadata.create_all(engine)


if __name__ == "__main__":
    main()
