"""Upgrade the desktop database with Alembic and seed built-in data."""

# This executable script directory is intentionally not a Python package.

from __future__ import annotations

from engine.database.bootstrap import initialize_database


def main() -> None:
    """Apply packaged revisions and idempotent seeds to the configured database."""
    initialize_database()


if __name__ == "__main__":
    main()
