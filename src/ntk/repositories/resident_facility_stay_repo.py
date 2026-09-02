"""Persistence operations for resident facility stays."""

from __future__ import annotations

import typing

from sqlalchemy import func, or_
from sqlmodel import col, select

from ntk.models.sql.resident import Resident, ResidentFacilityStay

if typing.TYPE_CHECKING:
    from datetime import datetime

    from sqlmodel import Session


class ResidentFacilityStayRepo:
    """Persist and resolve resident facility stays."""

    def __init__(self, session: Session) -> None:
        """Initialize the repository with a database session."""
        self.session = session

    def create(self, stay: ResidentFacilityStay) -> ResidentFacilityStay:
        """Persist a stay or return its existing natural-identity match."""
        existing = self._get_by_identity(
            facility_id=stay.facility_id,
            resident_id=stay.resident_id,
            admitted_at=stay.admitted_at,
        )
        if existing is not None:
            return existing

        if stay.facility_resident_identifier is not None:
            stay.facility_resident_identifier = (
                stay.facility_resident_identifier.strip() or None
            )
        self.session.add(stay)
        self.session.commit()
        self.session.refresh(stay)
        return stay

    def get_by_id(self, stay_id: int) -> ResidentFacilityStay | None:
        """Return a stay by its database identifier."""
        return self.session.get(ResidentFacilityStay, stay_id)

    def get_by_facility_identifier(
        self,
        *,
        facility_id: int,
        facility_resident_identifier: str,
        effective_at: datetime | None = None,
    ) -> ResidentFacilityStay | None:
        """Resolve a facility-scoped resident identifier at a point in time."""
        identifier = facility_resident_identifier.strip()
        if not identifier:
            return None
        statement = select(ResidentFacilityStay).where(
            ResidentFacilityStay.facility_id == facility_id,
            ResidentFacilityStay.facility_resident_identifier == identifier,
        )
        if effective_at is not None:
            statement = statement.where(
                or_(
                    col(ResidentFacilityStay.admitted_at).is_(None),
                    col(ResidentFacilityStay.admitted_at) <= effective_at,
                ),
                or_(
                    col(ResidentFacilityStay.discharged_at).is_(None),
                    col(ResidentFacilityStay.discharged_at) >= effective_at,
                ),
            )
        statement = statement.order_by(
            col(ResidentFacilityStay.admitted_at).desc().nulls_last(),
            col(ResidentFacilityStay.id).desc(),
        )
        return self.session.exec(statement).first()

    def get_by_resident_name(
        self,
        *,
        facility_id: int,
        resident_name: str,
        effective_at: datetime | None = None,
    ) -> ResidentFacilityStay | None:
        """Resolve a normalized resident name within a facility."""
        normalized_name = self._normalize_name(resident_name)
        if not normalized_name:
            return None
        statement = (
            select(ResidentFacilityStay)
            .join(Resident)
            .where(
                ResidentFacilityStay.facility_id == facility_id,
                func.lower(Resident.name) == normalized_name.casefold(),
            )
        )
        if effective_at is not None:
            statement = statement.where(
                or_(
                    col(ResidentFacilityStay.admitted_at).is_(None),
                    col(ResidentFacilityStay.admitted_at) <= effective_at,
                ),
                or_(
                    col(ResidentFacilityStay.discharged_at).is_(None),
                    col(ResidentFacilityStay.discharged_at) >= effective_at,
                ),
            )
        statement = statement.order_by(
            col(ResidentFacilityStay.admitted_at).desc().nulls_last(),
            col(ResidentFacilityStay.id).desc(),
        )
        return self.session.exec(statement).first()

    def get_by_resident_id(self, resident_id: int) -> list[ResidentFacilityStay]:
        """Return all stays for a resident, newest admission first."""
        statement = (
            select(ResidentFacilityStay)
            .where(ResidentFacilityStay.resident_id == resident_id)
            .order_by(
                col(ResidentFacilityStay.admitted_at).desc().nulls_last(),
                col(ResidentFacilityStay.id).desc(),
            )
        )
        return list(self.session.exec(statement).all())

    def _get_by_identity(
        self,
        *,
        facility_id: int,
        resident_id: int,
        admitted_at: datetime | None,
    ) -> ResidentFacilityStay | None:
        statement = select(ResidentFacilityStay).where(
            ResidentFacilityStay.facility_id == facility_id,
            ResidentFacilityStay.resident_id == resident_id,
        )
        if admitted_at is None:
            statement = statement.where(
                col(ResidentFacilityStay.admitted_at).is_(None),
            )
        else:
            statement = statement.where(
                ResidentFacilityStay.admitted_at == admitted_at,
            )
        return self.session.exec(statement).first()

    @staticmethod
    def _normalize_name(name: str) -> str:
        return " ".join(name.split())
