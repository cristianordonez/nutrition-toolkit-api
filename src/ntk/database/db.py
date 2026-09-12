from __future__ import annotations

import typing

from sqlmodel import Session, create_engine

from ntk.models.settings import SETTINGS
from ntk.repositories.facility_repo import FacilityRepo
from ntk.repositories.food_repo import FoodRepo
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
    """Seed built-in data after Alembic has created the database schema.

    This function intentionally does not create or alter tables. Deployments and
    local environments must run ``alembic upgrade head`` before startup.
    """
    with Session(engine) as session:
        PermissionRepo(session).seed_defaults()
        FacilityRepo(session).seed_defaults()
        FoodRepo(session).seed_default_formulas()
