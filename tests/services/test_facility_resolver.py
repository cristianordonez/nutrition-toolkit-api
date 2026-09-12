from __future__ import annotations

import typing

import pytest
from sqlmodel import Session, SQLModel, create_engine

from ntk.repositories.facility_repo import FacilityRepo
from ntk.services.facility_resolver import FacilityResolver


@pytest.fixture
def repository() -> typing.Generator[FacilityRepo, None, None]:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield FacilityRepo(session)


def test_resolve_matches_canonical_name_and_configured_alias(
    repository: FacilityRepo,
) -> None:
    facility = repository.seed_defaults()[0]
    resolver = FacilityResolver(repository)

    assert resolver.resolve(" Embassy   Manor ") is facility
    assert resolver.resolve("Embassy Manor at Edison") is facility


def test_resolve_does_not_create_unknown_extracted_facility(
    repository: FacilityRepo,
) -> None:
    resolver = FacilityResolver(repository)

    assert resolver.resolve("Noisy report heading") is None
    assert repository.get_all() == []


def test_register_trusted_creates_explicit_facility(
    repository: FacilityRepo,
) -> None:
    facility = FacilityResolver(repository).register_trusted(
        name="Sunrise Care",
        facility_identifier="FAC-1",
    )

    assert facility.name == "Sunrise Care"
    assert facility.facility_identifier == "FAC-1"


def test_resolve_rejects_conflicting_name_and_identifier(
    repository: FacilityRepo,
) -> None:
    resolver = FacilityResolver(repository)
    resolver.register_trusted(name="First", facility_identifier="FAC-1")
    resolver.register_trusted(name="Second", facility_identifier="FAC-2")

    with pytest.raises(ValueError, match="different facilities"):
        resolver.resolve("Second", facility_identifier="FAC-1")
