from __future__ import annotations

from datetime import date

import pytest
from sqlmodel import Session, SQLModel, create_engine

from ntk.models.sql.facility import Facility
from ntk.models.sql.person import Person, PersonAssessment
from ntk.pipelines.person.ingestion.extract.pcc_progress_notes import ParsedProgressNote
from ntk.repositories.facility_repo import FacilityRepo
from ntk.repositories.person_repo import PersonRepo
from ntk.services.facility_resolver import FacilityResolver
from ntk.services.person.person_service import PersonService


def _service(session: Session) -> PersonService:
    facility_repository = FacilityRepo(session)
    for identifier, name in (
        ("FAC-1", "Facility One"),
        ("FAC-FIRST", "First Facility"),
        ("FAC-SECOND", "Second Facility"),
    ):
        facility_repository.create(
            Facility(facility_identifier=identifier, name=name),
        )
    return PersonService(
        PersonRepo(session),
        FacilityResolver(facility_repository),
    )


def test_resolve_or_create_prefers_facility_scoped_identifier() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        service = _service(session)
        created = service.resolve_or_create_person(
            facility_name="Facility One",
            source_person_identifier="R-7",
            source_person_name="Doe, Jane",
        )
        resolved = service.resolve_or_create_person(
            facility_name="Facility One",
            source_person_identifier="R-7",
            source_person_name="Jane Changed",
            height_in=64,
        )

        assert resolved.id == created.id
        assert resolved.height_in == 64  # noqa: PLR2004


def test_resolve_or_create_uses_name_and_birth_date_without_identifier() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    birth_date = date(1940, 1, 2)

    with Session(engine) as session:
        service = _service(session)
        created = service.resolve_or_create_person(
            source_person_name="Doe, Jane",
            date_of_birth=birth_date,
        )
        resolved = service.find_person(
            first_name=" jane ",
            last_name="DOE",
            birth_date=birth_date,
        )

        assert resolved is not None
        assert resolved.id == created.id


def test_richer_report_enriches_unique_name_only_person() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    birth_date = date(1955, 11, 1)

    with Session(engine) as session:
        service = _service(session)
        assert service.facility_resolver is not None
        facility = service.facility_resolver.resolve("Facility One")
        assert facility is not None
        existing = service.repository.create(
            Person(name="Dickow, Denise", facility_id=facility.id),
        )

        resolved = service.resolve_or_create_person(
            facility_name="Facility One",
            source_person_identifier="210407",
            source_person_name="DICKOW, DENISE",
            date_of_birth=birth_date,
        )

        assert resolved.id == existing.id
        assert resolved.date_of_birth == birth_date
        assert resolved.person_identifier == "210407"
        assert len(service.repository.get_all()) == 1


def test_report_without_birth_date_reuses_unique_dated_name() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    birth_date = date(1955, 11, 1)

    with Session(engine) as session:
        service = _service(session)
        existing = service.resolve_or_create_person(
            facility_name="Facility One",
            source_person_name="Dickow, Denise",
            date_of_birth=birth_date,
        )

        resolved = service.resolve_or_create_person(
            facility_name="Facility One",
            source_person_identifier="210407",
            source_person_name="Dickow, Denise",
        )

        assert resolved.id == existing.id
        assert resolved.date_of_birth == birth_date
        assert resolved.person_identifier == "210407"
        assert len(service.repository.get_all()) == 1


def test_resolve_or_create_rejects_insufficient_identity() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    with (
        Session(engine) as session,
        pytest.raises(ValueError, match="Cannot create a person"),
    ):
        _service(session).resolve_or_create_person(source_person_name="Doe, Jane")


def test_identifier_match_rejects_conflicting_birth_date() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        service = _service(session)
        service.resolve_or_create_person(
            facility_name="Facility One",
            source_person_identifier="R-7",
            source_person_name="Doe, Jane",
            date_of_birth=date(1940, 1, 2),
        )

        with pytest.raises(ValueError, match="different birth date"):
            service.resolve_or_create_person(
                facility_name="Facility One",
                source_person_identifier="R-7",
                source_person_name="Doe, Jane",
                date_of_birth=date(1941, 1, 2),
            )


def test_natural_identity_survives_a_facility_transfer() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    birth_date = date(1940, 1, 2)

    with Session(engine) as session:
        service = _service(session)
        original = service.resolve_or_create_person(
            facility_name="First Facility",
            source_person_identifier="OLD-1",
            source_person_name="Doe, Jane",
            date_of_birth=birth_date,
        )
        original_facility_id = original.facility_id
        transferred = service.resolve_or_create_person(
            facility_name="Second Facility",
            source_person_identifier="NEW-1",
            source_person_name="DOE, JANE",
            date_of_birth=birth_date,
        )

        assert transferred.id == original.id
        assert (
            service.repository.get_by_identifier(
                "OLD-1",
                facility_id=original_facility_id,
            )
            is None
        )
        assert (
            service.repository.get_by_identifier(
                "NEW-1",
                facility_id=transferred.facility_id,
            )
            is not None
        )
        assert transferred.facility is not None
        assert transferred.facility.name == "Second Facility"


def test_unresolved_facility_does_not_replace_current_assignment() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    birth_date = date(1940, 1, 2)

    with Session(engine) as session:
        service = _service(session)
        person = service.resolve_or_create_person(
            facility_name="Facility One",
            source_person_identifier="R-7",
            source_person_name="Doe, Jane",
            date_of_birth=birth_date,
        )
        original_facility_id = person.facility_id

        resolved = service.resolve_or_create_person(
            facility_name="Noisy report heading",
            source_person_identifier="UNKNOWN-7",
            source_person_name="Doe, Jane",
            date_of_birth=birth_date,
        )

        assert resolved.id == person.id
        assert resolved.facility_id == original_facility_id
        assert (
            service.repository.get_by_identifier(
                "R-7",
                facility_id=original_facility_id,
            )
            is not None
        )
        assert service.facility_resolver is not None
        assert service.facility_resolver.resolve("Noisy report heading") is None


def test_unresolved_progress_note_facility_does_not_block_natural_identity() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    birth_date = date(1940, 1, 2)

    with Session(engine) as session:
        service = _service(session)
        person = service.resolve_or_create_person(
            source_person_name="Doe, Jane",
            date_of_birth=birth_date,
        )
        note = ParsedProgressNote(
            source_person_name="DOE, JANE",
            facility_name="Noisy report heading",
            date_of_birth=birth_date,
            note_text="Nutrition follow-up",
            raw_text="Nutrition follow-up",
            source_filename="notes.pdf",
        )

        resolved = service.resolve_progress_note(note)

        assert resolved is not None
        assert resolved.id == person.id


def test_get_person_detail_by_internal_id_includes_assessments() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        service = _service(session)
        person = service.resolve_or_create_person(
            facility_name="Facility One",
            source_person_identifier="R-7",
            source_person_name="Doe, Jane",
        )
        assessment = service.repository.create_assessment(
            PersonAssessment(
                person_id=person.id,  # ty: ignore[invalid-argument-type]
                content="Nutrition assessment",
                content_hash="assessment-hash",
                assessment_date=date(2026, 9, 7),
                created_by="dietitian",
            ),
        )

        detail = service.get_person_detail_by_id(person.id)  # ty: ignore[invalid-argument-type]

        assert detail.person_id == person.id
        assert detail.person_identifier == "R-7"
        assert [item.id for item in detail.assessments] == [assessment.id]
        assert "Nutrition assessment" in detail.model_dump_json()


def test_get_person_detail_scopes_identifier_to_facility() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        facility = Facility(facility_identifier="FAC-1", name="Facility One")
        session.add(facility)
        session.commit()
        session.refresh(facility)
        service = _service(session)
        service.resolve_or_create_person(
            source_person_name="Doe, Jane",
            source_person_identifier="R-7",
            facility_id=facility.id,
        )

        detail = service.get_person_detail(
            "R-7",
            facility_identifier="FAC-1",
        )

        assert detail.name == "Doe, Jane"
