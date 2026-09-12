"""Persistence operations for care facilities."""

from __future__ import annotations

import typing

from sqlmodel import col, select

from ntk.defaults import DEFAULT_FACILITIES, DefaultFacility
from ntk.models.sql.facility import Facility, normalize_facility_name

if typing.TYPE_CHECKING:
    from sqlmodel import Session


class FacilityRepo:
    """Persist and retrieve facilities."""

    def __init__(self, session: Session) -> None:
        """Initialize the repository with a database session."""
        self.session = session

    def create(self, facility: Facility) -> Facility:
        """Persist an explicitly supplied facility or return its existing match."""
        facility_identifier = self._normalize_identifier(
            facility.facility_identifier,
        )
        name = self._display_name(facility.name)
        if not name:
            msg = "Facility name cannot be empty"
            raise ValueError(msg)
        existing = (
            self.get_by_facility_identifier(facility_identifier)
            if facility_identifier is not None
            else None
        )
        name_match = self.get_by_name(name)
        if existing is not None and name_match not in (None, existing):
            msg = "Facility identifier and normalized name match different facilities"
            raise ValueError(msg)
        existing = existing or name_match
        if existing is not None:
            return existing

        facility.facility_identifier = facility_identifier
        facility.name = name
        facility.normalized_name = normalize_facility_name(name)
        self.session.add(facility)
        self.session.commit()
        self.session.refresh(facility)
        return facility

    def upsert_default(self, default: DefaultFacility) -> Facility:
        """Create or update one trusted configured facility."""
        identifier = self._normalize_identifier(default.facility_identifier)
        name = self._display_name(default.name)
        candidates = [
            candidate
            for candidate in (
                (
                    self.get_by_facility_identifier(identifier)
                    if identifier is not None
                    else None
                ),
                self.get_by_name(name),
                *(self.get_by_name(alias) for alias in default.aliases),
            )
            if candidate is not None
        ]
        candidate_ids = {candidate.id for candidate in candidates}
        if len(candidate_ids) > 1:
            msg = f"Configured aliases for {name!r} match multiple facilities"
            raise ValueError(msg)
        existing = candidates[0] if candidates else None
        if existing is None:
            return self.create(
                Facility(name=name, facility_identifier=identifier),
            )
        existing.name = name
        existing.normalized_name = normalize_facility_name(name)
        if identifier is not None:
            existing.facility_identifier = identifier
        self.session.add(existing)
        self.session.commit()
        self.session.refresh(existing)
        return existing

    def seed_defaults(self) -> list[Facility]:
        """Idempotently seed every trusted configured facility."""
        return [self.upsert_default(default) for default in DEFAULT_FACILITIES]

    def get_by_id(self, facility_id: int) -> Facility | None:
        """Return a facility by its database identifier."""
        return self.session.get(Facility, facility_id)

    def get_by_facility_identifier(
        self,
        facility_identifier: str,
    ) -> Facility | None:
        """Return a facility by its external identifier."""
        normalized = self._normalize_identifier(facility_identifier)
        if normalized is None:
            return None
        statement = select(Facility).where(
            Facility.facility_identifier == normalized,
        )
        return self.session.exec(statement).first()

    def get_by_name(self, name: str) -> Facility | None:
        """Return a facility using a normalized, case-insensitive name."""
        normalized_name = normalize_facility_name(name)
        if not normalized_name:
            return None
        statement = select(Facility).where(
            Facility.normalized_name == normalized_name,
        )
        return self.session.exec(statement).first()

    def get_all(self) -> list[Facility]:
        """Return all facilities ordered by name and database ID."""
        statement = select(Facility).order_by(
            Facility.normalized_name,
            col(Facility.id),
        )
        return list(self.session.exec(statement).all())

    @staticmethod
    def _display_name(name: str) -> str:
        """Collapse surrounding and repeated whitespace in a display name."""
        return " ".join(name.split())

    @staticmethod
    def _normalize_identifier(identifier: str | None) -> str | None:
        """Normalize an optional external facility identifier."""
        normalized = " ".join((identifier or "").split())
        return normalized or None
