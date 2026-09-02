from __future__ import annotations

import typing

from sqlmodel import Session, SQLModel, create_engine

# Import every SQL model so its table is registered before create_all.
import ntk.models.sql  # noqa: F401
from ntk.models.settings import SETTINGS
from ntk.repositories.permission_repo import PermissionRepo

if typing.TYPE_CHECKING:
    from collections.abc import Generator


engine = create_engine(
    str(SETTINGS.database_url),
    echo=False,
    pool_size=SETTINGS.pool_size,
    max_overflow=SETTINGS.max_overflow,
)


def get_session() -> Generator[Session, None, None]:
    """Generate database session."""
    with Session(engine, expire_on_commit=False) as session:
        yield session


def initialize_database() -> None:
    """Create registered tables and seed built-in permissions explicitly."""
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        PermissionRepo(session).seed_defaults()
