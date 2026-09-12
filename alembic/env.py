"""Alembic environment backed by the application's SQLModel metadata."""

# Alembic's standard script directory is intentionally not a Python package.
# ruff: noqa: INP001

from __future__ import annotations

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from sqlmodel import SQLModel

# Import the complete SQL model package before reading SQLModel.metadata.
import ntk.models.sql  # noqa: F401
from alembic import context
from ntk.models.settings import SETTINGS

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

connection_url = config.attributes.get("connection_url", SETTINGS.database_url)
config.set_main_option("sqlalchemy.url", str(connection_url).replace("%", "%%"))
target_metadata = SQLModel.metadata


def include_name(
    name: str | None,
    type_: str,
    _parent_names: dict[str, str | None],
) -> bool:
    """Exclude infrastructure tables not owned by this application."""
    return not (type_ == "table" and name == "session")


def run_migrations_offline() -> None:
    """Run migrations without creating an Engine."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        include_name=include_name,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations using the configured application database."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            include_name=include_name,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
