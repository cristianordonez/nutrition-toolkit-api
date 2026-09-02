"""Persistence operations for care facilities."""

from __future__ import annotations

import typing

from sqlalchemy import func
from sqlmodel import col, select

from ntk.models.sql.facility import Facility

if typing.TYPE_CHECKING:
    from sqlmodel import Session


class FacilityRepo:
    """Persist and retrieve facilities."""

    def __init__(self, session: Session) -> None:
        """Initialize the repository with a database session."""
        self.session = session

    def create(self, facility: Facility) -> Facility:
        """Persist a facility or return its existing external-ID match."""
        facility_id = facility.facility_id.strip()
        name = self._normalize_name(facility.name)
        if not facility_id or not name:
            msg = "Facility identifier and name cannot be empty"
            raise ValueError(msg)

        existing = self.get_by_facility_id(facility_id)
        if existing is not None:
            return existing

        facility.facility_id = facility_id
        facility.name = name
        self.session.add(facility)
        self.session.commit()
        self.session.refresh(facility)
        return facility

    def get_by_id(self, facility_id: int) -> Facility | None:
        """Return a facility by its database identifier."""
        return self.session.get(Facility, facility_id)

    def get_by_facility_id(self, facility_id: str) -> Facility | None:
        """Return a facility by its external identifier."""
        statement = select(Facility).where(
            Facility.facility_id == facility_id.strip(),
        )
        return self.session.exec(statement).first()

    def get_by_name(self, name: str) -> Facility | None:
        """Return a facility using a normalized, case-insensitive name."""
        normalized_name = self._normalize_name(name)
        if not normalized_name:
            return None
        statement = select(Facility).where(
            func.lower(Facility.name) == normalized_name.casefold(),
        )
        return self.session.exec(statement).first()

    def get_all(self) -> list[Facility]:
        """Return all facilities ordered by name and database ID."""
        statement = select(Facility).order_by(
            func.lower(Facility.name),
            col(Facility.id),
        )
        return list(self.session.exec(statement).all())

    @staticmethod
    def _normalize_name(name: str) -> str:
        """Collapse surrounding and repeated whitespace in a facility name."""
        return " ".join(name.split())
