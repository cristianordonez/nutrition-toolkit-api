"""Shared session boundaries for controllers and application services."""

from __future__ import annotations

import typing
from contextlib import contextmanager

from sqlmodel import Session

from engine.database.db import engine

if typing.TYPE_CHECKING:
    from collections.abc import Generator


def get_session() -> Generator[Session, None, None]:
    """Yield a session whose loaded values survive a commit."""
    with Session(engine, expire_on_commit=False) as session:
        yield session


@contextmanager
def controller_session(
    session: Session | None = None,
) -> Generator[Session, None, None]:
    """Reuse a caller-owned session or close a new session after the operation."""
    if session is not None:
        yield session
    else:
        yield from get_session()


settings_session = controller_session
