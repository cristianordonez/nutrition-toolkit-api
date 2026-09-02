from __future__ import annotations

import typing
from datetime import UTC, date, datetime

import pytest
from sqlmodel import Session, SQLModel, create_engine

import ntk.models.sql  # noqa: F401
from ntk.models.sql.clinical import ResidentOrder
from ntk.models.sql.extracted_fact import ExtractedFact
from ntk.models.sql.facility import Facility
from ntk.models.sql.resident import Resident, ResidentFacilityStay
from ntk.repositories.facility_repo import FacilityRepo
from ntk.repositories.resident_facility_stay_repo import ResidentFacilityStayRepo
from ntk.repositories.resident_repo import ResidentRepo
from ntk.services.resident_data.extract.pcc_progress_notes import ParsedProgressNote
from ntk.services.resident_data.resident_resolver import ResidentResolver
from ntk.utils.misc import require_id


@pytest.fixture
def session() -> typing.Generator[Session, None, None]:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture
def resolver(session: Session) -> ResidentResolver:
    return ResidentResolver(
        resident_repository=ResidentRepo(session),
        facility_repository=FacilityRepo(session),
        stay_repository=ResidentFacilityStayRepo(session),
    )


def create_resident_stay(
    session: Session,
    resolver: ResidentResolver,
) -> tuple[int, int, int]:
    facility = resolver.facility_repository.create(
        Facility(facility_id="FAC-1", name="Sunrise Care"),
    )
    resident = Resident(name="Jane Doe")
    session.add(resident)
    session.commit()
    session.refresh(resident)
    stay = resolver.stay_repository.create(
        ResidentFacilityStay(
            resident_id=require_id(resident.id),
            facility_id=require_id(facility.id),
            facility_resident_identifier="RES-1",
            admitted_at=datetime(2026, 1, 1, tzinfo=UTC),
        ),
    )
    return require_id(resident.id), require_id(facility.id), require_id(stay.id)


def test_resolve_prefers_facility_resident_identifier(
    session: Session,
    resolver: ResidentResolver,
) -> None:
    resident_id, facility_id, stay_id = create_resident_stay(session, resolver)

    resolution = resolver.resolve(
        facility_name=" sunrise   CARE ",
        facility_resident_identifier="RES-1",
        resident_name="Wrong Name",
        effective_at=datetime(2026, 6, 1, tzinfo=UTC),
    )

    assert resolution is not None
    assert resolution.resident_id == resident_id
    assert resolution.facility_id == facility_id
    assert resolution.resident_facility_stay_id == stay_id


def test_resolve_falls_back_to_resident_name_within_facility(
    session: Session,
    resolver: ResidentResolver,
) -> None:
    resident_id, facility_id, stay_id = create_resident_stay(session, resolver)

    resolution = resolver.resolve(
        facility_name="Sunrise Care",
        facility_resident_identifier=None,
        resident_name="  JANE   doe ",
        effective_at=datetime(2026, 6, 1, tzinfo=UTC),
    )

    assert resolution is not None
    assert resolution.resident_id == resident_id
    assert resolution.facility_id == facility_id
    assert resolution.resident_facility_stay_id == stay_id


def test_resolve_does_not_fall_back_to_name_when_identifier_is_present(
    session: Session,
    resolver: ResidentResolver,
) -> None:
    create_resident_stay(session, resolver)

    resolution = resolver.resolve(
        facility_name="Sunrise Care",
        facility_resident_identifier="UNKNOWN",
        resident_name="Jane Doe",
        effective_at=datetime(2026, 6, 1, tzinfo=UTC),
    )

    assert resolution is None


def test_resolve_or_create_creates_missing_identity_graph(
    resolver: ResidentResolver,
) -> None:
    effective_at = datetime(2026, 7, 1, tzinfo=UTC)

    resolution = resolver.resolve_or_create(
        facility_name="  New   Facility ",
        facility_resident_identifier=" RES-2 ",
        resident_name="  John   Smith ",
        effective_at=effective_at,
    )

    facility = resolver.facility_repository.get_by_name("New Facility")
    resident = resolver.resident_repository.get_by_name("John Smith")
    assert facility is not None
    assert resident is not None
    assert facility.facility_id.startswith("generated:")
    assert resolution.facility_id == facility.id
    assert resolution.resident_id == resident.id
    stay = resolver.stay_repository.get_by_id(
        require_id(resolution.resident_facility_stay_id),
    )
    assert stay is not None
    assert stay.facility_resident_identifier == "RES-2"
    assert stay.admitted_at == effective_at.replace(tzinfo=None)


def test_resolve_or_create_reuses_identifier_stay_outside_effective_date(
    session: Session,
    resolver: ResidentResolver,
) -> None:
    resident_id, facility_id, stay_id = create_resident_stay(session, resolver)

    resolution = resolver.resolve_or_create(
        facility_name="Sunrise Care",
        facility_resident_identifier="RES-1",
        resident_name="Different Name",
        effective_at=datetime(2025, 1, 1, tzinfo=UTC),
    )

    assert resolution.resident_id == resident_id
    assert resolution.facility_id == facility_id
    assert resolution.resident_facility_stay_id == stay_id
    assert resolver.stay_repository.get_by_resident_id(resident_id) == [
        resolver.stay_repository.get_by_id(stay_id),
    ]


def test_progress_note_resolution_adapters(
    resolver: ResidentResolver,
) -> None:
    note = ParsedProgressNote(
        facility_resident_identifier="RES-3",
        resident_name="Alex Resident",
        facility_name="Progress Facility",
        date_of_birth=date(1946, 2, 1),
        sex="Female",
        height_in=64.5,
        note_date=datetime(2026, 8, 1, tzinfo=UTC),
        note_text="Progress note",
        raw_text="Progress note",
        source_filename="notes.pdf",
    )

    assert resolver.resolve_progress_note(note) is None
    created = resolver.resolve_or_create_progress_note(note)
    assert created.resident_facility_stay_id is None
    assert resolver.resolve_progress_note(note) is None
    resident = resolver.resident_repository.get_by_id(created.resident_id)
    assert resident is not None
    assert resident.date_of_birth == date(1946, 2, 1)
    assert resident.sex == "f"
    assert resident.height_in == note.height_in


def test_same_name_in_another_facility_creates_a_distinct_resident(
    session: Session,
    resolver: ResidentResolver,
) -> None:
    expected_resident_count = 2
    existing_resident_id, _, _ = create_resident_stay(session, resolver)

    created = resolver.resolve_or_create_resident(
        facility_name="Another Facility",
        facility_resident_identifier="OTHER-1",
        resident_name="Jane Doe",
    )
    repeated = resolver.resolve_or_create_resident(
        facility_name="Another Facility",
        facility_resident_identifier="OTHER-1",
        resident_name="Jane Doe",
    )

    assert created.resident_id != existing_resident_id
    assert repeated.resident_id == created.resident_id
    assert len(resolver.resident_repository.get_all()) == expected_resident_count


def test_new_identifier_with_duplicate_name_and_different_dob_creates_new_resident(
    session: Session,
    resolver: ResidentResolver,
) -> None:
    facility = resolver.facility_repository.create(
        Facility(facility_id="FAC-PATEL", name="Patel Facility"),
    )
    existing = Resident(
        name="Patel, Sushilaben",
        date_of_birth=date(1930, 1, 18),
        sex="f",
    )
    session.add(existing)
    session.commit()
    existing_order = ResidentOrder(
        resident_id=require_id(existing.id),
        summary="Order belonging to the 1930 resident",
        status="active",
    )
    session.add(existing_order)
    session.commit()
    resolver.stay_repository.create(
        ResidentFacilityStay(
            resident_id=require_id(existing.id),
            facility_id=require_id(facility.id),
            facility_resident_identifier="EN140518",
        ),
    )

    created = resolver.resolve_or_create_resident(
        facility_name="Patel Facility",
        facility_resident_identifier="EN140519",
        resident_name="Patel, Sushilaben",
        date_of_birth=date(1945, 5, 26),
        sex="F",
    )

    assert created.resident_id != existing.id
    resident = resolver.resident_repository.get_by_id(created.resident_id)
    assert resident is not None
    assert resident.date_of_birth == date(1945, 5, 26)
    assert (
        resolver.resident_repository.get_assessment_records(
            created.resident_id,
        ).orders
        == []
    )
    assert resolver.resident_repository.get_assessment_records(
        require_id(existing.id),
    ).orders == [existing_order]


def test_same_name_and_dob_reuses_resident_across_facility_identifiers(
    resolver: ResidentResolver,
) -> None:
    first = resolver.resolve_or_create_resident(
        facility_name="Venetian Care and Rehabilitation Center - SNF",
        facility_resident_identifier="193966",
        resident_name="Patel, Sushilaben",
        date_of_birth=date(1945, 5, 26),
        sex="F",
    )
    second = resolver.resolve_or_create_resident(
        facility_name="Embassy Manor at Edison",
        facility_resident_identifier="EN140519",
        resident_name="Patel, Sushilaben",
        date_of_birth=date(1945, 5, 26),
        sex="F",
    )

    assert second.resident_id == first.resident_id
    assert len(resolver.resident_repository.get_all()) == 1
    resident = resolver.resident_repository.get_by_identifier_mapping(
        facility_id=require_id(second.facility_id),
        facility_resident_identifier="EN140519",
    )
    assert resident is not None
    assert resident.id == first.resident_id


def test_fact_identifier_with_conflicting_dob_does_not_capture_new_resident(
    session: Session,
    resolver: ResidentResolver,
) -> None:
    facility = resolver.facility_repository.create(
        Facility(facility_id="FAC-CONFLICT", name="Conflict Facility"),
    )
    existing = Resident(
        name="Patel, Sushilaben",
        date_of_birth=date(1930, 1, 18),
        sex="f",
    )
    session.add(existing)
    session.commit()
    session.add(
        ExtractedFact(
            resident_id=require_id(existing.id),
            facility_id=require_id(facility.id),
            resident_name=existing.name,
            facility_resident_identifier="EN140519",
            facility_name=facility.name,
            fact_type="weight",
            payload={"weight_lb": 138},
            confidence=1.0,
        ),
    )
    session.commit()

    created = resolver.resolve_or_create_resident(
        facility_name=facility.name,
        facility_resident_identifier="EN140519",
        resident_name=existing.name,
        date_of_birth=date(1945, 5, 26),
        sex="F",
    )

    assert created.resident_id != existing.id
    resident = resolver.resident_repository.get_by_id(created.resident_id)
    assert resident is not None
    assert resident.date_of_birth == date(1945, 5, 26)
