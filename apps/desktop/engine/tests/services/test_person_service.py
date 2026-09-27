from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from sqlmodel import Session, SQLModel, create_engine

from engine.models.sql.clinical_source import (
    ClinicalSource,
    ClinicalSourceKind,
    ExtractionStatus,
)
from engine.models.sql.person import Person
from engine.pipelines.person.ingestion.extract.pcc_progress_notes import (
    ParsedProgressNote,
)
from engine.repositories.clinical_source_repo import ClinicalSourceRepo
from engine.repositories.person_repo import PersonRepo
from engine.services.person.person_service import PersonService


def _service(session: Session) -> PersonService:
    return PersonService(PersonRepo(session))


def test_resolve_or_create_reuses_a_person_by_identifier() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        service = _service(session)
        created = service.resolve_or_create_person(
            source_person_identifier="R-7",
            source_person_name="Doe, Jane",
        )
        resolved = service.resolve_or_create_person(
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
        existing = service.repository.create(Person(name="Dickow, Denise"))

        resolved = service.resolve_or_create_person(
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
            source_person_name="Dickow, Denise",
            date_of_birth=birth_date,
        )

        resolved = service.resolve_or_create_person(
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
            source_person_identifier="R-7",
            source_person_name="Doe, Jane",
            date_of_birth=date(1940, 1, 2),
        )

        with pytest.raises(ValueError, match="different birth date"):
            service.resolve_or_create_person(
                source_person_identifier="R-7",
                source_person_name="Doe, Jane",
                date_of_birth=date(1941, 1, 2),
            )


def test_a_new_identifier_does_not_relabel_a_known_person() -> None:
    """Name and birth date still resolve a person whose chart number changed.

    This used to describe a facility transfer, where a second identifier was
    allowed to replace the first. With no facility, a second identifier for a
    matched person is just a conflicting claim, so the person is reused and
    the identifier already on file is kept rather than silently rewritten.
    """
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    birth_date = date(1940, 1, 2)

    with Session(engine) as session:
        service = _service(session)
        original = service.resolve_or_create_person(
            source_person_identifier="OLD-1",
            source_person_name="Doe, Jane",
            date_of_birth=birth_date,
        )
        resolved = service.resolve_or_create_person(
            source_person_identifier="NEW-1",
            source_person_name="DOE, JANE",
            date_of_birth=birth_date,
        )

        assert resolved.id == original.id
        assert resolved.person_identifier == "OLD-1"
        assert len(service.repository.get_all()) == 1


def test_a_clinical_note_resolves_by_natural_identity() -> None:
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
            date_of_birth=birth_date,
            note_text="Nutrition follow-up",
            raw_text="Nutrition follow-up",
            source_filename="notes.pdf",
        )

        resolved = service.resolve_clinical_note(note)

        assert resolved is not None
        assert resolved.id == person.id


def test_get_person_detail_by_internal_id_includes_clinical_notes() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        service = _service(session)
        person = service.resolve_or_create_person(
            source_person_identifier="R-7",
            source_person_name="Doe, Jane",
        )
        note = ClinicalSourceRepo(session).create(
            ClinicalSource(
                person_id=person.id,  # ty: ignore[invalid-argument-type]
                source_kind=ClinicalSourceKind.PROGRESS_NOTE,
                effective_at=datetime(2026, 9, 7, tzinfo=UTC),
                note_type="Nutrition/Dietary",
                content="Nutrition assessment",
                raw_content="Nutrition assessment",
                source_key="nutrition-assessment",
                extraction_status=ExtractionStatus.EXTRACTED,
            ),
        )

        detail = service.get_person_detail_by_id(person.id)  # ty: ignore[invalid-argument-type]

        assert detail.person_id == person.id
        assert detail.person_identifier == "R-7"
        assert [item.id for item in detail.clinical_notes] == [note.id]
        assert "Nutrition assessment" in detail.model_dump_json()


def test_get_person_detail_resolves_by_identifier() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        service = _service(session)
        service.resolve_or_create_person(
            source_person_name="Doe, Jane",
            source_person_identifier="R-7",
        )

        detail = service.get_person_detail("R-7")

        assert detail.name == "Doe, Jane"
