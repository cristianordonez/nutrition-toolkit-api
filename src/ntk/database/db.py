from __future__ import annotations

import logging
import typing

from sqlmodel import Session, SQLModel, create_engine, select

import ntk.models  # noqa: F401
from ntk.defaults import DEFAULT_PERMISSIONS
from ntk.models.api_key import Permission
from ntk.models.settings import settings

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


def seed_permissions(session: Session) -> None:
    """Create initial permissions.

    :param session: Database session
    """
    existing = {
        permission.name for permission in session.exec(select(Permission)).all()
    }
    permissions = [
        Permission(name=name) for name in DEFAULT_PERMISSIONS if name not in existing
    ]
    if permissions:
        session.add_all(permissions)
        session.commit()


SQLModel.metadata.create_all(engine)

seed_permissions(next(get_session()))
