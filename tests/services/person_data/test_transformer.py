from __future__ import annotations

import hashlib
import typing
from datetime import UTC, date, datetime

import pytest
from sqlmodel import Session, SQLModel, create_engine

from ntk.models.extracted_fact_create import (
    AppetitePayload,
    DietPayload,
    EdemaPayload,
    ExtractedFactCreate,
    GIObservationPayload,
    LabPayload,
    MealIntakePayload,
)
from ntk.models.sql.clinical import (
    AppetiteLevel,
    GISymptom,
    PersonAppetiteObservation,
    PersonGIObservation,
)
from ntk.models.sql.facility import Facility
from ntk.models.sql.person import Person, PersonEdema, PersonLab
from ntk.pipelines.person.ingestion.transformer import ExtractedFactTransformer
from ntk.repositories.facility_repo import FacilityRepo
from ntk.repositories.person_repo import PersonRepo
from ntk.services.facility_resolver import FacilityResolver
from ntk.services.person.person_service import PersonService

if typing.TYPE_CHECKING:
    import pathlib

_OBSERVED_AT = datetime(2026, 8, 27, tzinfo=UTC)


class StubPersonService:
    def __init__(self, persons: dict[str, Person]) -> None:
        self.persons = persons

    def resolve_or_create_person(
        self,
        *,
        source_person_identifier: str | None = None,
        **_identity: object,
    ) -> Person:
        if source_person_identifier is None:
            msg = "source_person_identifier is required"
            raise ValueError(msg)
        return self.persons[source_person_identifier]


def _stub(persons: dict[str, Person]) -> PersonService:
    return typing.cast("PersonService", StubPersonService(persons))


def test_transformer_builds_provenance_and_related_model(
    tmp_path: pathlib.Path,
) -> None:
    path = tmp_path / "report.pdf"
    path.write_bytes(b"person report")
    person = Person(id=7, name="Doe, Jane")
    create = ExtractedFactCreate(
        source_person_identifier="RES1",
        payload=LabPayload(name="Albumin", result="3.0", observed_at=_OBSERVED_AT),
        confidence=0.9,
    )

    transformed = ExtractedFactTransformer(_stub({"RES1": person})).transform(
        path,
        [create],
        extractor_name="TestExtractor",
    )

    assert transformed.document.checksum == (
        f"sha256:{hashlib.sha256(b'person report').hexdigest()}"
    )
    fact = transformed.extracted_facts[0]
    related = transformed.related_models[0]
    assert fact.person_id == 7  # noqa: PLR2004
    assert fact.source_person_identifier == "RES1"
    assert isinstance(related, PersonLab)
    assert related.person_id == 7  # noqa: PLR2004
    assert related.extracted_fact is fact


def test_transformer_persists_identity_and_demographics(
    tmp_path: pathlib.Path,
) -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    path = tmp_path / "weights.pdf"
    path.write_bytes(b"person demographics")

    with Session(engine) as session:
        repository = PersonRepo(session)
        facility_repository = FacilityRepo(session)
        facility = facility_repository.create(
            Facility(facility_identifier="FAC-1", name="Facility"),
        )
        resolver = FacilityResolver(facility_repository)
        service = PersonService(repository, resolver)
        transformed = ExtractedFactTransformer(service).transform(
            path,
            [
                ExtractedFactCreate(
                    facility_name="Facility",
                    source_person_identifier="RES1",
                    source_person_name="Doe, Jane",
                    date_of_birth=date(1946, 2, 1),
                    sex="Female",
                    height_in=64.5,
                    payload=EdemaPayload(
                        location=None,
                        observed_at=_OBSERVED_AT,
                    ),
                    confidence=1,
                ),
            ],
            extractor_name="TestExtractor",
        )

        person = repository.get_by_identifier(
            "RES1",
            facility_id=facility.id,
        )
        assert person is not None
        assert person.first_name == "Jane"
        assert person.last_name == "Doe"
        assert person.date_of_birth == date(1946, 2, 1)
        assert person.sex == "f"
        assert transformed.extracted_facts[0].facility_id == person.facility_id
        assert transformed.extracted_facts[0].facility_id == facility.id
        assert transformed.document.facility_id == facility.id
        assert isinstance(transformed.related_models[0], PersonEdema)
        assert transformed.related_models[0].location == "Unspecified"


def test_source_facility_does_not_follow_person_current_facility(
    tmp_path: pathlib.Path,
) -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    path = tmp_path / "historical-report.pdf"
    path.write_bytes(b"historical report")

    with Session(engine) as session:
        facility_repository = FacilityRepo(session)
        current = facility_repository.create(
            Facility(facility_identifier="CURRENT", name="Current Facility"),
        )
        source = facility_repository.create(
            Facility(facility_identifier="SOURCE", name="Source Facility"),
        )
        person = Person(id=7, name="Doe, Jane", facility_id=current.id)

        transformed = ExtractedFactTransformer(
            _stub({"RES1": person}),
            FacilityResolver(facility_repository),
        ).transform(
            path,
            [
                ExtractedFactCreate(
                    source_person_identifier="RES1",
                    facility_name="Source Facility",
                    payload=LabPayload(
                        name="Albumin",
                        result="3.0",
                        observed_at=_OBSERVED_AT,
                    ),
                    confidence=1,
                ),
            ],
            extractor_name="TestExtractor",
        )

        assert person.facility_id == current.id
        assert transformed.extracted_facts[0].facility_id == source.id
        assert transformed.document.facility_id == source.id


def test_mixed_facility_document_has_no_single_facility(
    tmp_path: pathlib.Path,
) -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    path = tmp_path / "mixed-report.csv"
    path.write_text("mixed report", encoding="utf-8")

    with Session(engine) as session:
        facility_repository = FacilityRepo(session)
        first = facility_repository.create(Facility(name="First Facility"))
        second = facility_repository.create(Facility(name="Second Facility"))
        persons = {
            "RES1": Person(id=7, name="Doe, Jane"),
            "RES2": Person(id=8, name="Smith, John"),
        }
        transformed = ExtractedFactTransformer(
            _stub(persons),
            FacilityResolver(facility_repository),
        ).transform(
            path,
            [
                ExtractedFactCreate(
                    source_person_identifier=identifier,
                    facility_name=facility_name,
                    payload=LabPayload(
                        name="Albumin",
                        result="3.0",
                        observed_at=_OBSERVED_AT,
                    ),
                    confidence=1,
                )
                for identifier, facility_name in (
                    ("RES1", "First Facility"),
                    ("RES2", "Second Facility"),
                )
            ],
            extractor_name="TestExtractor",
        )

        assert transformed.document.facility_id is None
        assert {fact.facility_id for fact in transformed.extracted_facts} == {
            first.id,
            second.id,
        }


def test_identical_payloads_for_different_persons_are_retained(
    tmp_path: pathlib.Path,
) -> None:
    path = tmp_path / "shared.csv"
    path.write_text("shared report", encoding="utf-8")
    persons = {
        "RES1": Person(id=7, name="Doe, Jane"),
        "RES2": Person(id=8, name="Smith, John"),
    }
    facts = [
        ExtractedFactCreate(
            source_person_identifier=identifier,
            payload=MealIntakePayload(
                min_percent=75,
                max_percent=75,
                observed_at=_OBSERVED_AT,
            ),
            confidence=1,
        )
        for identifier in persons
    ]

    transformed = ExtractedFactTransformer(_stub(persons)).transform(
        path,
        facts,
        extractor_name="UnknownDocument",
    )

    assert {fact.person_id for fact in transformed.extracted_facts} == {7, 8}


def test_transformer_requires_person_identity(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "report.txt"
    path.write_text("person report", encoding="utf-8")
    fact = ExtractedFactCreate(
        payload=EdemaPayload(location="Lower extremities", observed_at=_OBSERVED_AT),
        confidence=1,
    )

    with pytest.raises(ValueError, match="source_person_identifier is required"):
        ExtractedFactTransformer(_stub({})).transform(
            path,
            [fact],
            extractor_name="UnknownDocument",
        )


def test_transformer_keeps_observed_and_effective_times_distinct(
    tmp_path: pathlib.Path,
) -> None:
    path = tmp_path / "orders.pdf"
    path.write_bytes(b"orders")
    person = Person(id=7, name="Doe, Jane")
    transformed = ExtractedFactTransformer(_stub({"RES1": person})).transform(
        path,
        [
            ExtractedFactCreate(
                source_person_identifier="RES1",
                payload=DietPayload(
                    diet_type="Renal",
                    observed_at=datetime(2026, 8, 28, tzinfo=UTC),
                    source_revision_date=date(2026, 8, 27),
                ),
                confidence=1,
            ),
        ],
        extractor_name="PccOrderReportExtractor",
    )

    assert transformed.extracted_facts[0].observed_at == datetime(
        2026,
        8,
        28,
        tzinfo=UTC,
    )
    assert transformed.extracted_facts[0].effective_at is None


def test_transformer_creates_separate_appetite_and_gi_observations(
    tmp_path: pathlib.Path,
) -> None:
    path = tmp_path / "progress-notes.pdf"
    path.write_bytes(b"Reports nausea and poor appetite")
    person = Person(id=7, name="Doe, Jane")
    transformed = ExtractedFactTransformer(_stub({"RES1": person})).transform(
        path,
        [
            ExtractedFactCreate(
                source_person_identifier="RES1",
                payload=GIObservationPayload(
                    symptom=GISymptom.NAUSEA,
                    observed_at=_OBSERVED_AT,
                ),
                confidence=1,
            ),
            ExtractedFactCreate(
                source_person_identifier="RES1",
                payload=AppetitePayload(
                    appetite=AppetiteLevel.POOR,
                    observed_at=_OBSERVED_AT,
                ),
                confidence=1,
            ),
        ],
        extractor_name="UnknownDocument",
    )

    assert isinstance(transformed.related_models[0], PersonGIObservation)
    assert isinstance(transformed.related_models[1], PersonAppetiteObservation)
    assert transformed.related_models[0].observation_key
    assert transformed.related_models[1].observation_key
    assert transformed.extracted_facts[0].source is not None
    assert transformed.extracted_facts[1].source is not None
