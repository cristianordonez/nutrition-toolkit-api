"""Person identity resolution and person-detail operations."""

from __future__ import annotations

import typing

from ntk.models.sql.person import Person, parse_person_name
from ntk.services.person.detail_builder import PersonDetailBuilder
from ntk.utils.misc import require_id

if typing.TYPE_CHECKING:
    from datetime import date

    from ntk.models.person_detail import PersonDetail
    from ntk.pipelines.person.ingestion.extract.pcc_progress_notes import (
        ParsedProgressNote,
    )
    from ntk.repositories.person_repo import PersonRepo
    from ntk.services.facility_resolver import FacilityResolver


class PersonService:
    """Centralize person lookup, creation, and context construction."""

    def __init__(
        self,
        repository: PersonRepo,
        facility_resolver: FacilityResolver | None = None,
        person_detail_builder: PersonDetailBuilder | None = None,
    ) -> None:
        """Store person and optional facility resolution dependencies."""
        self.repository = repository
        self.facility_resolver = facility_resolver
        self.person_detail_builder = person_detail_builder or PersonDetailBuilder()

    def find_person(  # noqa: PLR0913
        self,
        *,
        person_id: int | None = None,
        source_person_identifier: str | None = None,
        facility_id: int | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        birth_date: date | None = None,
        source_person_name: str | None = None,
    ) -> Person | None:
        """Resolve one person using internal ID, external ID, or name and DOB."""
        if person_id is not None:
            return self.repository.get_by_id(person_id)
        if source_person_identifier:
            person = self.repository.get_by_identifier(
                source_person_identifier,
                facility_id=facility_id,
            )
            if person is not None:
                return person
        if source_person_name and (not first_name or not last_name):
            first_name, last_name = parse_person_name(source_person_name)
        if first_name and last_name and birth_date is not None:
            person = self.repository.get_by_name_and_birth_date(
                first_name,
                last_name,
                birth_date,
            )
            if person is not None:
                return person
        if first_name and last_name:
            return self.repository.get_compatible_by_name(
                first_name,
                last_name,
                birth_date=birth_date,
                person_identifier=source_person_identifier,
                facility_id=facility_id,
            )
        return None

    def resolve_or_create_person(  # noqa: C901, PLR0913
        self,
        *,
        facility_name: str | None = None,
        facility_id: int | None = None,
        source_person_identifier: str | None = None,
        source_person_name: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        date_of_birth: date | None = None,
        sex: str | None = None,
        height_in: float | None = None,
    ) -> Person:
        """Resolve deterministically, creating a person when identity is enough."""
        source_person_identifier = (
            " ".join(source_person_identifier.split())
            if source_person_identifier
            else None
        )
        if facility_id is None and facility_name:
            facility = self._require_facility_resolver().resolve(facility_name)
            facility_id = require_id(facility.id) if facility is not None else None
        if source_person_name and (not first_name or not last_name):
            first_name, last_name = parse_person_name(source_person_name)
        identifier_match = (
            self.repository.get_by_identifier(
                source_person_identifier,
                facility_id=facility_id,
            )
            if source_person_identifier
            else None
        )
        natural_match = (
            self.repository.get_by_name_and_birth_date(
                first_name,
                last_name,
                date_of_birth,
            )
            if first_name and last_name and date_of_birth is not None
            else None
        )
        if (
            natural_match is not None
            and identifier_match is not None
            and natural_match.id != identifier_match.id
        ):
            msg = "Person name and birth date conflict with person identifier"
            raise ValueError(msg)
        if natural_match is not None:
            facility_changed = (
                facility_id is not None
                and natural_match.facility_id is not None
                and natural_match.facility_id != facility_id
            )
            natural_match = self.repository.update_demographics(
                natural_match,
                sex=sex,
                height_in=height_in,
            )
            if facility_id is not None:
                natural_match = self.repository.assign_facility(
                    natural_match,
                    facility_id,
                )
            if source_person_identifier and (
                natural_match.person_identifier is None or facility_changed
            ):
                natural_match = self.repository.assign_identifier(
                    natural_match,
                    source_person_identifier,
                    replace=facility_changed,
                )
            return natural_match
        if identifier_match is not None:
            self._validate_identity(
                identifier_match,
                facility_id=facility_id,
                date_of_birth=date_of_birth,
            )
            return self.repository.update_demographics(
                identifier_match,
                date_of_birth=date_of_birth,
                sex=sex,
                height_in=height_in,
                facility_id=facility_id,
                person_identifier=source_person_identifier,
            )

        compatible_name_match = (
            self.repository.get_compatible_by_name(
                first_name,
                last_name,
                birth_date=date_of_birth,
                person_identifier=source_person_identifier,
                facility_id=facility_id,
            )
            if first_name and last_name
            else None
        )
        if compatible_name_match is not None:
            self._validate_identity(
                compatible_name_match,
                facility_id=facility_id,
                date_of_birth=date_of_birth,
            )
            return self.repository.update_demographics(
                compatible_name_match,
                date_of_birth=date_of_birth,
                sex=sex,
                height_in=height_in,
                facility_id=facility_id,
                person_identifier=source_person_identifier,
            )

        has_natural_identity = bool(first_name and last_name and date_of_birth)
        has_source_identifier = bool(source_person_identifier)
        if not (has_natural_identity or has_source_identifier):
            msg = (
                "Cannot create a person without first name, last name, and birth "
                "date or a person identifier"
            )
            raise ValueError(msg)
        display_name = " ".join((source_person_name or "").split())
        if not display_name:
            display_name = ", ".join(
                part for part in (last_name or "", first_name or "") if part
            )
        return self.repository.create(
            Person(
                name=display_name,
                first_name=first_name or "",
                last_name=last_name or "",
                date_of_birth=date_of_birth,
                facility_id=facility_id,
                person_identifier=source_person_identifier,
                sex=sex,
                height_in=height_in,
            ),
        )

    def resolve_progress_note(self, note: ParsedProgressNote) -> Person | None:
        """Resolve an existing person for a parsed progress note."""
        facility = (
            self.facility_resolver.resolve(note.facility_name)
            if self.facility_resolver is not None and note.facility_name
            else None
        )
        return self.find_person(
            source_person_identifier=note.source_person_identifier,
            facility_id=require_id(facility.id) if facility is not None else None,
            source_person_name=note.source_person_name,
            birth_date=note.date_of_birth,
        )

    def resolve_or_create_progress_note(self, note: ParsedProgressNote) -> Person:
        """Resolve or create the person for a parsed progress note."""
        return self.resolve_or_create_person(
            facility_name=note.facility_name,
            source_person_identifier=note.source_person_identifier,
            source_person_name=note.source_person_name,
            date_of_birth=note.date_of_birth,
            sex=note.sex,
            height_in=note.height_in,
        )

    def get_person_detail(
        self,
        source_person_identifier: str,
        *,
        facility_identifier: str | None = None,
    ) -> PersonDetail:
        """Return prepared context for an external person identifier."""
        facility = (
            self._require_facility_resolver().resolve(
                facility_identifier=facility_identifier,
            )
            if facility_identifier is not None
            else None
        )
        if facility_identifier is not None and facility is None:
            message = f"Facility {facility_identifier!r} was not found"
            raise LookupError(message)
        person = self.find_person(
            source_person_identifier=source_person_identifier,
            facility_id=require_id(facility.id) if facility is not None else None,
        )
        if person is None:
            message = f"Person {source_person_identifier!r} was not found"
            if facility_identifier is not None:
                message += f" at facility {facility_identifier!r}"
            raise LookupError(message)
        return self._get_person_detail(person)

    def get_person_detail_by_id(
        self,
        person_id: int,
    ) -> PersonDetail:
        """Return prepared context for an internal person database ID."""
        person = self.repository.get_by_id(person_id)
        if person is None:
            msg = f"Person {person_id} was not found"
            raise LookupError(msg)
        return self._get_person_detail(person)

    def _get_person_detail(
        self,
        person: Person,
    ) -> PersonDetail:
        records = self.repository.get_assessment_records(require_id(person.id))
        return self.person_detail_builder.build(person, records)

    def _require_facility_resolver(self) -> FacilityResolver:
        if self.facility_resolver is None:
            msg = "A facility resolver is required for this operation"
            raise RuntimeError(msg)
        return self.facility_resolver

    @staticmethod
    def _validate_identity(
        person: Person,
        *,
        facility_id: int | None,
        date_of_birth: date | None,
    ) -> None:
        if (
            person.date_of_birth
            and date_of_birth
            and person.date_of_birth != date_of_birth
        ):
            msg = "Person identifier matched a different birth date"
            raise ValueError(msg)
        if person.facility_id and facility_id and person.facility_id != facility_id:
            msg = "Person is already associated with a different facility"
            raise ValueError(msg)


__all__ = ["PersonService"]
