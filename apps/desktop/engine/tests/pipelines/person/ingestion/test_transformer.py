from __future__ import annotations

import hashlib
import typing
from datetime import UTC, date, datetime

import pytest
from sqlmodel import Session, SQLModel, create_engine

from engine.models.clinical_fact_registry import hydrate_fact
from engine.models.clinical_facts import (
    PersonAppetiteObservation,
    PersonDiet,
    PersonEdema,
    PersonGIObservation,
    PersonLab,
)
from engine.models.clinical_vocab import AppetiteLevel, GISymptom
from engine.models.extracted_fact_create import (
    AppetitePayload,
    DietPayload,
    EdemaPayload,
    ExtractedFactCreate,
    GIObservationPayload,
    LabPayload,
    MealIntakePayload,
)
from engine.models.sql.person import Person
from engine.pipelines.person.ingestion.transformer import ClinicalFactTransformer
from engine.repositories.person_repo import PersonRepo
from engine.services.person.person_service import PersonService

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

    transformed = ClinicalFactTransformer(_stub({"RES1": person})).transform(
        path,
        [create],
        extractor_name="TestExtractor",
    )

    assert transformed.document.checksum == (
        f"sha256:{hashlib.sha256(b'person report').hexdigest()}"
    )
    fact = transformed.clinical_facts[0]
    related = hydrate_fact(fact)
    assert fact.person_id == 7  # noqa: PLR2004
    assert isinstance(related, PersonLab)
    assert related.person_id == 7  # noqa: PLR2004
    assert fact.source is transformed.clinical_sources[0]


def test_transformer_persists_identity_and_demographics(
    tmp_path: pathlib.Path,
) -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    path = tmp_path / "weights.pdf"
    path.write_bytes(b"person demographics")

    with Session(engine) as session:
        repository = PersonRepo(session)
        service = PersonService(repository)
        transformed = ClinicalFactTransformer(service).transform(
            path,
            [
                ExtractedFactCreate(
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
        )
        assert person is not None
        assert person.first_name == "Jane"
        assert person.last_name == "Doe"
        assert person.date_of_birth == date(1946, 2, 1)
        assert person.sex == "f"
        related = hydrate_fact(transformed.clinical_facts[0])
        assert isinstance(related, PersonEdema)
        assert related.location == "Unspecified"


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

    transformed = ClinicalFactTransformer(_stub(persons)).transform(
        path,
        facts,
        extractor_name="UnknownDocument",
    )

    assert {fact.person_id for fact in transformed.clinical_facts} == {7, 8}


def test_transformer_requires_person_identity(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "report.txt"
    path.write_text("person report", encoding="utf-8")
    fact = ExtractedFactCreate(
        payload=EdemaPayload(location="Lower extremities", observed_at=_OBSERVED_AT),
        confidence=1,
    )

    with pytest.raises(ValueError, match="source_person_identifier is required"):
        ClinicalFactTransformer(_stub({})).transform(
            path,
            [fact],
            extractor_name="UnknownDocument",
        )


def test_transformer_keeps_observed_and_effective_times_distinct(
    tmp_path: pathlib.Path,
) -> None:
    """The report's print time and the order's revision date are not the same date.

    ``observed_at`` is when the report was printed: identical for every row in
    a run, and no evidence about any of them. The revision date is the day the
    order was written or last changed, which is the only true clinical date
    these records carry. Keeping them apart is what lets an order last revised
    eleven months ago be told from one written today.
    """
    path = tmp_path / "orders.pdf"
    path.write_bytes(b"orders")
    person = Person(id=7, name="Doe, Jane")
    transformed = ClinicalFactTransformer(_stub({"RES1": person})).transform(
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

    assert transformed.clinical_facts[0].observed_at == datetime(
        2026,
        8,
        28,
        tzinfo=UTC,
    )
    assert transformed.clinical_facts[0].effective_at == datetime(
        2026,
        8,
        27,
        tzinfo=UTC,
    )
    related = hydrate_fact(transformed.clinical_facts[0])
    assert isinstance(related, PersonDiet)
    assert related.effective_at == datetime(
        2026,
        8,
        27,
        tzinfo=UTC,
    )


def test_transformer_creates_separate_appetite_and_gi_observations(
    tmp_path: pathlib.Path,
) -> None:
    path = tmp_path / "progress-notes.pdf"
    path.write_bytes(b"Reports nausea and poor appetite")
    person = Person(id=7, name="Doe, Jane")
    transformed = ClinicalFactTransformer(_stub({"RES1": person})).transform(
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

    first = hydrate_fact(transformed.clinical_facts[0])
    second = hydrate_fact(transformed.clinical_facts[1])
    assert isinstance(first, PersonGIObservation)
    assert isinstance(second, PersonAppetiteObservation)
    assert first.observation_key
    assert second.observation_key
    assert transformed.clinical_facts[0].source is not None
    assert transformed.clinical_facts[1].source is not None
