from __future__ import annotations

import typing
from datetime import UTC, datetime

import pytest
from sqlmodel import Session, SQLModel, create_engine

from ntk.models.sql.facility import Facility
from ntk.models.sql.resident import Resident, ResidentFacilityStay
from ntk.repositories.resident_facility_stay_repo import ResidentFacilityStayRepo
from ntk.utils.misc import require_id


@pytest.fixture
def session() -> typing.Generator[Session, None, None]:
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture
def resident_and_facility(session: Session) -> tuple[int, int]:
    resident = Resident(name="Jane Doe")
    facility = Facility(facility_id="FAC-1", name="Sunrise Care")
    session.add_all([resident, facility])
    session.commit()
    session.refresh(resident)
    session.refresh(facility)
    return require_id(resident.id), require_id(facility.id)


def test_create_persists_and_normalizes_identifier(
    session: Session,
    resident_and_facility: tuple[int, int],
) -> None:
    resident_id, facility_id = resident_and_facility
    repository = ResidentFacilityStayRepo(session)

    stay = repository.create(
        ResidentFacilityStay(
            resident_id=resident_id,
            facility_id=facility_id,
            facility_resident_identifier="  RES-1  ",
        ),
    )

    assert stay.id is not None
    assert stay.facility_resident_identifier == "RES-1"
    assert repository.get_by_id(stay.id) is stay


def test_create_returns_existing_natural_identity(
    session: Session,
    resident_and_facility: tuple[int, int],
) -> None:
    resident_id, facility_id = resident_and_facility
    repository = ResidentFacilityStayRepo(session)
    admitted_at = datetime(2026, 1, 1, tzinfo=UTC)
    existing = repository.create(
        ResidentFacilityStay(
            resident_id=resident_id,
            facility_id=facility_id,
            admitted_at=admitted_at,
        ),
    )

    duplicate = repository.create(
        ResidentFacilityStay(
            resident_id=resident_id,
            facility_id=facility_id,
            admitted_at=admitted_at,
        ),
    )

    assert duplicate is existing
    assert repository.get_by_resident_id(resident_id) == [existing]


def test_get_by_facility_identifier_honors_effective_date(
    session: Session,
    resident_and_facility: tuple[int, int],
) -> None:
    resident_id, facility_id = resident_and_facility
    repository = ResidentFacilityStayRepo(session)
    old_stay = repository.create(
        ResidentFacilityStay(
            resident_id=resident_id,
            facility_id=facility_id,
            facility_resident_identifier="RES-1",
            admitted_at=datetime(2025, 1, 1, tzinfo=UTC),
            discharged_at=datetime(2025, 12, 31, tzinfo=UTC),
        ),
    )
    current_stay = repository.create(
        ResidentFacilityStay(
            resident_id=resident_id,
            facility_id=facility_id,
            facility_resident_identifier="RES-1",
            admitted_at=datetime(2026, 1, 1, tzinfo=UTC),
        ),
    )

    assert (
        repository.get_by_facility_identifier(
            facility_id=facility_id,
            facility_resident_identifier=" RES-1 ",
            effective_at=datetime(2025, 6, 1, tzinfo=UTC),
        )
        is old_stay
    )
    assert (
        repository.get_by_facility_identifier(
            facility_id=facility_id,
            facility_resident_identifier="RES-1",
            effective_at=datetime(2026, 6, 1, tzinfo=UTC),
        )
        is current_stay
    )
    assert (
        repository.get_by_facility_identifier(
            facility_id=facility_id,
            facility_resident_identifier=" ",
        )
        is None
    )


def test_get_by_resident_name_is_normalized_and_facility_scoped(
    session: Session,
    resident_and_facility: tuple[int, int],
) -> None:
    resident_id, facility_id = resident_and_facility
    other_facility = Facility(facility_id="FAC-2", name="Other")
    session.add(other_facility)
    session.commit()
    session.refresh(other_facility)
    other_facility_id = require_id(other_facility.id)
    repository = ResidentFacilityStayRepo(session)
    expected = repository.create(
        ResidentFacilityStay(
            resident_id=resident_id,
            facility_id=facility_id,
            admitted_at=datetime(2026, 1, 1, tzinfo=UTC),
        ),
    )
    repository.create(
        ResidentFacilityStay(
            resident_id=resident_id,
            facility_id=other_facility_id,
            admitted_at=datetime(2026, 1, 1, tzinfo=UTC),
        ),
    )

    assert (
        repository.get_by_resident_name(
            facility_id=facility_id,
            resident_name="  JANE   doe ",
            effective_at=datetime(2026, 6, 1, tzinfo=UTC),
        )
        is expected
    )
    assert (
        repository.get_by_resident_name(
            facility_id=facility_id,
            resident_name="missing",
        )
        is None
    )


def test_get_by_resident_id_orders_newest_first(
    session: Session,
    resident_and_facility: tuple[int, int],
) -> None:
    resident_id, facility_id = resident_and_facility
    repository = ResidentFacilityStayRepo(session)
    old_stay = repository.create(
        ResidentFacilityStay(
            resident_id=resident_id,
            facility_id=facility_id,
            admitted_at=datetime(2025, 1, 1, tzinfo=UTC),
        ),
    )
    new_stay = repository.create(
        ResidentFacilityStay(
            resident_id=resident_id,
            facility_id=facility_id,
            admitted_at=datetime(2026, 1, 1, tzinfo=UTC),
        ),
    )

    assert repository.get_by_resident_id(resident_id) == [new_stay, old_stay]
