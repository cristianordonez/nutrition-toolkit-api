from __future__ import annotations

import typing

from sqlmodel import col, select

from ntk.models.sql.resident import Resident, ResidentSnapshot

if typing.TYPE_CHECKING:
    from uuid import UUID

    from sqlmodel import Session


class ResidentRepo:
    def __init__(self, session: Session) -> None:
        """Get residents from database.

        :param session: database session
        """
        self.session = session

    def get_by_facility_id(self, facility_id: str) -> Resident | None:
        """Get resident by ID.

        :param facility_id: unique ID for user in facility
        :return: Resident model or None
        """
        statement = select(Resident).where(Resident.facility_id == facility_id)
        return self.session.exec(statement).first()

    def get_latest_snapshot(
        self,
        resident_id: UUID,
    ) -> ResidentSnapshot | None:
        """Get latest snapshot for given resident.

        :param resident_id: uuid
        :return: snapshot
        """
        statement = (
            select(ResidentSnapshot)
            .where(ResidentSnapshot.resident_id == resident_id)
            .order_by(col(ResidentSnapshot.created_at).desc())
            .limit(1)
        )
        return self.session.exec(statement).first()
