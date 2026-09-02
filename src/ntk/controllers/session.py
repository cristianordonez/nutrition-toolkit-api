"""Controller-owned database session boundary."""

from __future__ import annotations

import typing
from contextlib import contextmanager

from sqlmodel import Session

from ntk.database.db import engine

if typing.TYPE_CHECKING:
    from collections.abc import Generator


@contextmanager
def controller_session(
    session: Session | None,
) -> Generator[Session, None, None]:
    """Reuse an injected session or own one session for the controller call."""
    if session is not None:
        yield session
        return
    with Session(engine, expire_on_commit=False) as created_session:
        yield created_session
