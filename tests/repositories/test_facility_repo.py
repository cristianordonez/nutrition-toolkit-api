from __future__ import annotations

import typing

import pytest
from sqlmodel import Session, SQLModel, create_engine

from ntk.models.sql.facility import Facility
from ntk.repositories.facility_repo import FacilityRepo


@pytest.fixture
def session() -> typing.Generator[Session, None, None]:
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_create_persists_and_normalizes_facility(session: Session) -> None:
    repository = FacilityRepo(session)

    facility = repository.create(
        Facility(facility_identifier=" FAC-1 ", name="  Sunrise   Care  "),
    )

    assert facility.id is not None
    assert facility.facility_identifier == "FAC-1"
    assert facility.normalized_name == "sunrise care"
    assert facility.name == "Sunrise Care"
    assert repository.get_by_id(facility.id) is facility


def test_create_returns_existing_external_id_match(session: Session) -> None:
    repository = FacilityRepo(session)
    existing = repository.create(
        Facility(facility_identifier="FAC-1", name="Sunrise"),
    )

    duplicate = repository.create(
        Facility(facility_identifier=" FAC-1 ", name="Different Name"),
    )

    assert duplicate is existing
    assert repository.get_all() == [existing]


def test_get_by_facility_identifier_returns_matching_facility(
    session: Session,
) -> None:
    repository = FacilityRepo(session)
    facility = repository.create(
        Facility(facility_identifier="FAC-1", name="Sunrise"),
    )

    assert repository.get_by_facility_identifier(" FAC-1 ") is facility
    assert repository.get_by_facility_identifier("missing") is None


def test_get_by_name_is_normalized_and_case_insensitive(session: Session) -> None:
    repository = FacilityRepo(session)
    facility = repository.create(
        Facility(facility_identifier="FAC-1", name="Sunrise Care"),
    )

    assert repository.get_by_name("  SUNRISE   care ") is facility
    assert repository.get_by_name("missing") is None
    assert repository.get_by_name("   ") is None


def test_get_all_orders_facilities_by_name(session: Session) -> None:
    repository = FacilityRepo(session)
    zeta = repository.create(Facility(facility_identifier="FAC-2", name="Zeta"))
    alpha = repository.create(Facility(facility_identifier="FAC-1", name="alpha"))

    assert repository.get_all() == [alpha, zeta]


def test_create_allows_facility_without_external_identifier(session: Session) -> None:
    facility = FacilityRepo(session).create(Facility(name="Sunrise"))

    assert facility.facility_identifier is None


def test_create_rejects_empty_name(
    session: Session,
) -> None:
    repository = FacilityRepo(session)

    with pytest.raises(ValueError, match="name cannot be empty"):
        repository.create(Facility(facility_identifier="FAC-1", name="   "))
