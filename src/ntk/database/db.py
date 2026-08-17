from __future__ import annotations

import logging
import typing

from sqlmodel import Session, SQLModel, create_engine

# import all models so that they are initialized below
import ntk.models  # noqa: F401
from ntk.models.settings import SETTINGS
from ntk.repositories.permission_repo import PermissionRepo

if typing.TYPE_CHECKING:
    from collections.abc import Generator

logger = logging.getLogger(__name__)


engine = create_engine(
    str(SETTINGS.database_url),
    echo=False,
    pool_size=SETTINGS.pool_size,
    max_overflow=SETTINGS.max_overflow,
)


def get_session() -> Generator[Session, None, None]:
    """Generate database session."""
    with Session(engine) as session:
        yield session


SQLModel.metadata.create_all(engine)
session = next(get_session())
permission_repo = PermissionRepo(session)
permission_repo.seed_defaults()
