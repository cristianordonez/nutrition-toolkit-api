from __future__ import annotations

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from ntk.models.sql.extracted_fact import ExtractedFact
from ntk.models.sql.facility import Facility
from ntk.models.sql.resident import Resident, ResidentFacilityStay, ResidentIdentifier
from ntk.repositories.resident_repo import ResidentRepo


def test_resident_identifier_resolves_unique_resident() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        facility = Facility(facility_id="FAC-1", name="Facility One")
        resident = Resident(name="Resident One")
        session.add_all([facility, resident])
        session.commit()
        session.refresh(facility)
        session.refresh(resident)
        session.add(
            ResidentFacilityStay(
                facility_id=facility.id,  # ty: ignore[invalid-argument-type]
                resident_id=resident.id,  # ty: ignore[invalid-argument-type]
                facility_resident_identifier="R-1",
            ),
        )
        session.commit()

        resolved = ResidentRepo(session).get_by_resident_identifier(" R-1 ")

        assert resolved is not None
        assert resolved.id == resident.id


def test_resident_identifier_resolves_from_fact_without_stay() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        facility = Facility(facility_id="FAC-1", name="Facility One")
        resident = Resident(name="Resident One")
        session.add_all([facility, resident])
        session.commit()
        session.refresh(facility)
        session.refresh(resident)
        session.add(
            ExtractedFact(
                resident_id=resident.id,
                facility_id=facility.id,
                facility_resident_identifier="R-1",
                fact_key="fact-key",
                fact_type="lab",
                payload={},
                confidence=1.0,
            ),
        )
        session.commit()

        resolved = ResidentRepo(session).get_by_resident_identifier(
            "R-1",
            facility_id="FAC-1",
        )

        assert resolved is not None
        assert resolved.id == resident.id


def test_facility_identifier_mapping_reuses_one_resident() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    expected_height = 64

    with Session(engine) as session:
        facility = Facility(facility_id="FAC-1", name="Facility One")
        session.add(facility)
        session.commit()
        session.refresh(facility)
        repository = ResidentRepo(session)

        created = repository.create_for_facility_identifier(
            Resident(name="Resident One"),
            facility_id=facility.id,  # ty: ignore[invalid-argument-type]
            facility_resident_identifier=" R-1 ",
        )
        reused = repository.create_for_facility_identifier(
            Resident(name="Resident One", height_in=expected_height),
            facility_id=facility.id,  # ty: ignore[invalid-argument-type]
            facility_resident_identifier="R-1",
        )

        assert reused.id == created.id
        assert reused.height_in == expected_height
        assert len(repository.get_all()) == 1
        mapping = session.exec(select(ResidentIdentifier)).one()
        assert mapping.resident_id == created.id
        assert mapping.facility_resident_identifier == "R-1"

        resolved = repository.get_by_resident_identifier(
            "R-1",
            facility_id="FAC-1",
        )
        assert resolved is not None
        assert resolved.id == created.id


def test_competing_identifier_claim_discards_duplicate_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    expected_height = 65

    with Session(engine) as session:
        facility = Facility(facility_id="FAC-1", name="Facility One")
        canonical = Resident(name="Resident One")
        session.add_all([facility, canonical])
        session.commit()
        session.refresh(facility)
        session.refresh(canonical)
        repository = ResidentRepo(session)
        original_lookup = repository.get_by_identifier_mapping
        lookup_count = 0

        def simulate_competing_claim(
            *,
            facility_id: int,
            facility_resident_identifier: str,
        ) -> Resident | None:
            nonlocal lookup_count
            lookup_count += 1
            if lookup_count == 1:
                session.add(
                    ResidentIdentifier(
                        resident_id=canonical.id,  # ty: ignore[invalid-argument-type]
                        facility_id=facility_id,
                        facility_resident_identifier=(facility_resident_identifier),
                    ),
                )
                session.commit()
                return None
            return original_lookup(
                facility_id=facility_id,
                facility_resident_identifier=facility_resident_identifier,
            )

        monkeypatch.setattr(
            repository,
            "get_by_identifier_mapping",
            simulate_competing_claim,
        )

        resolved = repository.create_for_facility_identifier(
            Resident(name="Resident One", height_in=expected_height),
            facility_id=facility.id,  # ty: ignore[invalid-argument-type]
            facility_resident_identifier="R-1",
        )

        assert resolved.id == canonical.id
        assert resolved.height_in == expected_height
        assert len(repository.get_all()) == 1


def test_identifier_claim_rejects_persisted_resident_candidate() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        facility = Facility(facility_id="FAC-1", name="Facility One")
        resident = Resident(name="Resident One")
        session.add_all([facility, resident])
        session.commit()
        session.refresh(facility)
        session.refresh(resident)

        with pytest.raises(ValueError, match="new resident candidate"):
            ResidentRepo(session).create_for_facility_identifier(
                resident,
                facility_id=facility.id,  # ty: ignore[invalid-argument-type]
                facility_resident_identifier="R-1",
            )


def test_duplicate_identifier_requires_matching_facility() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        first_facility = Facility(facility_id="FAC-1", name="Facility One")
        second_facility = Facility(facility_id="FAC-2", name="Facility Two")
        first_resident = Resident(name="Resident One")
        second_resident = Resident(name="Resident Two")
        session.add_all(
            [first_facility, second_facility, first_resident, second_resident],
        )
        session.commit()
        for record in (
            first_facility,
            second_facility,
            first_resident,
            second_resident,
        ):
            session.refresh(record)
        session.add_all(
            [
                ResidentFacilityStay(
                    facility_id=first_facility.id,  # ty: ignore[invalid-argument-type]
                    resident_id=first_resident.id,  # ty: ignore[invalid-argument-type]
                    facility_resident_identifier="SHARED",
                ),
                ResidentFacilityStay(
                    facility_id=second_facility.id,  # ty: ignore[invalid-argument-type]
                    resident_id=second_resident.id,  # ty: ignore[invalid-argument-type]
                    facility_resident_identifier="SHARED",
                ),
            ],
        )
        session.commit()
        repository = ResidentRepo(session)

        with pytest.raises(LookupError, match="ambiguous"):
            repository.get_by_resident_identifier("SHARED")

        resolved = repository.get_by_resident_identifier(
            "SHARED",
            facility_id="FAC-2",
        )

        assert resolved is not None
        assert resolved.id == second_resident.id


def test_duplicate_identifier_within_facility_uses_unique_resident_name() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        facility = Facility(facility_id="FAC-1", name="Facility One")
        expected = Resident(name="Jane Doe")
        duplicate = Resident(name="John Doe")
        session.add_all([facility, expected, duplicate])
        session.commit()
        assert facility.id is not None
        assert expected.id is not None
        assert duplicate.id is not None
        session.add_all(
            [
                ExtractedFact(
                    resident_id=resident.id,
                    facility_id=facility.id,
                    facility_resident_identifier="732",
                    fact_key=f"fact-{resident.id}",
                    fact_type="lab",
                    payload={},
                    confidence=1.0,
                )
                for resident in (expected, duplicate)
            ],
        )
        session.commit()

        resolved = ResidentRepo(session).get_by_resident_identifier(
            "732",
            facility_id="FAC-1",
            resident_name=" jane   DOE ",
        )

        assert resolved is not None
        assert resolved.id == expected.id
