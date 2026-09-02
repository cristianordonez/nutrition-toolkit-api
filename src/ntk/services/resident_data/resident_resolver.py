from __future__ import annotations

import typing
from hashlib import sha256

from pydantic import BaseModel

from ntk.models.sql.facility import Facility
from ntk.models.sql.resident import Resident, ResidentFacilityStay
from ntk.utils.misc import require_id

if typing.TYPE_CHECKING:
    from datetime import date, datetime

    from ntk.repositories.facility_repo import FacilityRepo
    from ntk.repositories.resident_facility_stay_repo import ResidentFacilityStayRepo
    from ntk.repositories.resident_repo import ResidentRepo
    from ntk.services.resident_data.extract.pcc_progress_notes import (
        ParsedProgressNote,
    )


class ResidentResolution(BaseModel):
    resident_id: int
    resident_facility_stay_id: int | None = None
    facility_id: int | None = None


class ResidentResolver:
    def __init__(
        self,
        resident_repository: ResidentRepo,
        facility_repository: FacilityRepo,
        stay_repository: ResidentFacilityStayRepo,
    ) -> None:
        """Store repositories used to resolve and create resident identities."""
        self.resident_repository = resident_repository
        self.facility_repository = facility_repository
        self.stay_repository = stay_repository
        self._resident_cache: dict[
            tuple[int, str | None, str],
            ResidentResolution,
        ] = {}

    def __call__(
        self,
        note: ParsedProgressNote,
    ) -> ResidentResolution | None:
        """Resolve a parsed progress note to its persisted resident identity."""
        return self.resolve_progress_note(note)

    def resolve_progress_note(
        self,
        note: ParsedProgressNote,
    ) -> ResidentResolution | None:
        """Resolve an existing resident and stay for a progress note."""
        return self.resolve(
            facility_name=note.facility_name,
            facility_resident_identifier=note.facility_resident_identifier,
            resident_name=note.resident_name,
            effective_at=note.note_date,
        )

    def resolve_or_create_progress_note(
        self,
        note: ParsedProgressNote,
    ) -> ResidentResolution:
        """Resolve or create the resident identity for a progress note."""
        return self.resolve_or_create_resident(
            facility_name=note.facility_name,
            facility_resident_identifier=note.facility_resident_identifier,
            resident_name=note.resident_name,
            date_of_birth=note.date_of_birth,
            sex=note.sex,
            height_in=note.height_in,
            effective_at=note.note_date,
        )

    def resolve(
        self,
        *,
        facility_id: int | None = None,
        facility_name: str | None = None,
        facility_resident_identifier: str | None = None,
        resident_name: str | None = None,
        effective_at: datetime | None = None,
    ) -> ResidentResolution | None:
        """Resolve resident data from db."""
        if facility_id is None and facility_name is not None:
            facility = self.facility_repository.get_by_name(facility_name)
            if facility is not None:
                facility_id = require_id(facility.id)
        if facility_id is None:
            return None
        if facility_resident_identifier:
            stay = self.stay_repository.get_by_facility_identifier(
                facility_id=facility_id,
                facility_resident_identifier=(facility_resident_identifier),
                effective_at=effective_at,
            )
            if stay is not None:
                return self._from_stay(stay)
            return None
        if resident_name:
            stay = self.stay_repository.get_by_resident_name(
                facility_id=facility_id,
                resident_name=resident_name,
                effective_at=effective_at,
            )
            if stay is not None:
                return self._from_stay(stay)
        return None

    def resolve_stay(self, stay_id: int) -> ResidentResolution | None:
        """Resolve an explicitly supplied stay and link its unassigned facts."""
        stay = self.stay_repository.get_by_id(stay_id)
        return self._from_stay(stay) if stay is not None else None

    def resolve_or_create_resident(  # noqa: PLR0913
        self,
        *,
        facility_name: str | None,
        facility_resident_identifier: str | None,
        resident_name: str | None,
        date_of_birth: date | None = None,
        sex: str | None = None,
        height_in: float | None = None,
        effective_at: datetime | None = None,
    ) -> ResidentResolution:
        """Resolve identity clues without inventing a facility stay."""
        resolution = self.resolve(
            facility_name=facility_name,
            facility_resident_identifier=facility_resident_identifier,
            resident_name=resident_name,
            effective_at=effective_at,
        )
        if resolution is not None:
            resident = self.resident_repository.get_by_id(resolution.resident_id)
            if resident is not None:
                self.resident_repository.update_demographics(
                    resident,
                    date_of_birth=date_of_birth,
                    sex=sex,
                    height_in=height_in,
                )
            return resolution
        normalized_facility_name = self._normalize_required(
            facility_name,
            field_name="facility_name",
        )
        normalized_resident_name = self._normalize_required(
            resident_name,
            field_name="resident_name",
        )
        facility = self.facility_repository.get_by_name(normalized_facility_name)
        if facility is None:
            digest = sha256(normalized_facility_name.casefold().encode()).hexdigest()
            facility = self.facility_repository.create(
                Facility(
                    facility_id=f"generated:{digest}",
                    name=normalized_facility_name,
                ),
            )
        normalized_identifier = (
            " ".join(facility_resident_identifier.split())
            if facility_resident_identifier
            else None
        )
        facility_database_id = require_id(facility.id)
        cache_key = (
            facility_database_id,
            normalized_identifier.casefold() if normalized_identifier else None,
            normalized_resident_name.casefold(),
        )
        cached = self._resident_cache.get(cache_key)
        if cached is not None:
            resident = self.resident_repository.get_by_id(cached.resident_id)
            if resident is not None:
                self.resident_repository.update_demographics(
                    resident,
                    date_of_birth=date_of_birth,
                    sex=sex,
                    height_in=height_in,
                )
            return cached
        resident = self._identifier_candidate(
            normalized_identifier,
            facility_id=facility.facility_id,
            resident_name=normalized_resident_name,
            date_of_birth=date_of_birth,
        )
        if resident is None and date_of_birth is not None:
            resident = self.resident_repository.get_by_name_and_date_of_birth(
                normalized_resident_name,
                date_of_birth,
            )
            if resident is not None and normalized_identifier is not None:
                resident = self.resident_repository.claim_facility_identifier(
                    resident,
                    facility_id=facility_database_id,
                    facility_resident_identifier=normalized_identifier,
                )
        if resident is None and normalized_identifier is None:
            resident = self.resident_repository.get_by_name_and_facility(
                normalized_resident_name,
                facility_id=facility_database_id,
            )
        if resident is None:
            candidate = Resident(
                name=normalized_resident_name,
                date_of_birth=date_of_birth,
                sex=sex,
                height_in=height_in,
            )
            resident = (
                self.resident_repository.create_for_facility_identifier(
                    candidate,
                    facility_id=facility_database_id,
                    facility_resident_identifier=normalized_identifier,
                )
                if normalized_identifier is not None
                else self.resident_repository.create_unmatched(candidate)
            )
        else:
            resident = self.resident_repository.update_demographics(
                resident,
                date_of_birth=date_of_birth,
                sex=sex,
                height_in=height_in,
            )
        resolution = ResidentResolution(
            resident_id=require_id(resident.id),
            facility_id=facility_database_id,
        )
        self._resident_cache[cache_key] = resolution
        return resolution

    def _identifier_candidate(
        self,
        identifier: str | None,
        *,
        facility_id: str,
        resident_name: str,
        date_of_birth: date | None,
    ) -> Resident | None:
        """Reject fact-derived identity matches with contradictory DOBs."""
        if identifier is None:
            return None
        resident = self.resident_repository.get_by_resident_identifier(
            identifier,
            facility_id=facility_id,
            resident_name=resident_name,
        )
        if (
            resident is not None
            and date_of_birth is not None
            and resident.date_of_birth is not None
            and resident.date_of_birth != date_of_birth
        ):
            return None
        return resident

    def resolve_or_create(  # noqa: PLR0913
        self,
        *,
        facility_name: str | None,
        facility_resident_identifier: str | None,
        resident_name: str | None,
        date_of_birth: date | None = None,
        sex: str | None = None,
        height_in: float | None = None,
        effective_at: datetime | None = None,
    ) -> ResidentResolution:
        """Resolve identity clues, creating the missing identity graph."""
        resolution = self.resolve_or_create_resident(
            facility_name=facility_name,
            facility_resident_identifier=facility_resident_identifier,
            resident_name=resident_name,
            date_of_birth=date_of_birth,
            sex=sex,
            height_in=height_in,
            effective_at=effective_at,
        )
        if resolution.resident_facility_stay_id is not None:
            return resolution
        identifier = (
            facility_resident_identifier.strip()
            if facility_resident_identifier is not None
            else None
        ) or None
        facility_id = require_id(resolution.facility_id)
        if identifier is not None:
            stay = self.stay_repository.get_by_facility_identifier(
                facility_id=facility_id,
                facility_resident_identifier=identifier,
            )
            if stay is not None:
                return self._from_stay(stay)
        stay = self.stay_repository.create(
            ResidentFacilityStay(
                resident_id=resolution.resident_id,
                facility_id=facility_id,
                facility_resident_identifier=identifier,
                admitted_at=effective_at,
            ),
        )
        return self._from_stay(stay)

    def assign_unlinked_facts_to_stay(self, stay: ResidentFacilityStay) -> int:
        """Assign this stay to persisted facts that fall within its dates."""
        return self.resident_repository.assign_unlinked_facts_to_stay(stay)

    def _from_stay(self, stay: ResidentFacilityStay) -> ResidentResolution:
        self.assign_unlinked_facts_to_stay(stay)
        return ResidentResolution(
            resident_id=stay.resident_id,
            resident_facility_stay_id=require_id(stay.id),
            facility_id=stay.facility_id,
        )

    @staticmethod
    def _normalize_required(value: str | None, *, field_name: str) -> str:
        normalized = " ".join((value or "").split())
        if not normalized:
            msg = f"{field_name} is required to resolve resident identity"
            raise ValueError(msg)
        return normalized
