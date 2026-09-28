"""Alembic environment for packaged SQLite migrations and development tools."""

from __future__ import annotations

import typing
from logging.config import fileConfig

from alembic import context
from sqlalchemy import inspect
from sqlmodel import SQLModel
from sqlmodel.sql.sqltypes import AutoString

import engine.models.sql  # noqa: F401 - register the relational metadata
from engine.database.db import create_database_engine, database_url

if typing.TYPE_CHECKING:
    from alembic.autogenerate.api import AutogenContext
    from alembic.runtime.environment import NameFilterParentNames
    from sqlalchemy import Connection

config = context.config
if config.config_file_name is not None and config.get_section("loggers"):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = SQLModel.metadata
_VECTOR_TABLES = ("knowledge_chunk_vector", "ncp_note_vector")


def render_item(
    type_: str,
    item: object,
    _context: AutogenContext,
) -> str | typing.Literal[False]:
    """Render SQLModel strings as standalone SQLAlchemy migration types."""
    if type_ == "type" and isinstance(item, AutoString):
        return f"sa.String(length={item.length!r})" if item.length else "sa.String()"
    return False


def include_name(
    name: str | None,
    type_: str,
    _parent_names: NameFilterParentNames,
) -> bool:
    """Keep vec0 tables and their shadow tables out of autogeneration."""
    return not (
        type_ == "table"
        and name is not None
        and any(
            name == table or name.startswith(f"{table}_") for table in _VECTOR_TABLES
        )
    )


def run_migrations_offline() -> None:
    """Render SQL without opening the application's database."""
    context.configure(
        url="sqlite://",
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        transactional_ddl=True,
        render_as_batch=True,
        include_name=include_name,
        render_item=render_item,
    )
    with context.begin_transaction():
        context.run_migrations()


def _run(connection: Connection) -> None:
    tables = set(inspect(connection).get_table_names())
    if tables and "alembic_version" not in tables:
        msg = (
            "This SQLite database predates Alembic. Use a new NTK_DATABASE_PATH "
            "for this initial schema, or explicitly migrate the legacy database "
            "after backing it up. No existing tables have been changed."
        )
        raise RuntimeError(msg)
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        transactional_ddl=True,
        render_as_batch=True,
        include_name=include_name,
        render_item=render_item,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Reuse bootstrap's connection, or open a configured development database."""
    connection = config.attributes.get("connection")
    if connection is not None:
        _run(connection)
        return
    url = config.get_main_option("sqlalchemy.url") or database_url()
    database = create_database_engine(url)
    try:
        with database.connect() as connection:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            _run(connection)
            connection.commit()
    finally:
        database.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
