from __future__ import annotations

import logging
import typing

from sqlmodel import Session, SQLModel, create_engine

import ntk.models  # noqa: F401
from ntk.models.settings import settings
from ntk.repositories.permission import PermissionRepository

if typing.TYPE_CHECKING:
    from collections.abc import Generator

logger = logging.getLogger(__name__)


engine = create_engine(
    str(settings.database_url),
    echo=False,
    pool_size=settings.pool_size,
    max_overflow=settings.max_overflow,
)


def get_session() -> Generator[Session, None, None]:
    """Generate database session."""
    with Session(engine) as session:
        yield session


SQLModel.metadata.create_all(engine)
session = next(get_session())
permission_repo = PermissionRepository(session)
permission_repo.seed_defaults()
