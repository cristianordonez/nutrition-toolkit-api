from __future__ import annotations

import asyncio
import hashlib
import typing
from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest

from ntk.models.sql.clinical.weight import PersonWeight
from ntk.models.sql.facility import Facility
from ntk.models.sql.person import (
    NutritionCareProcessSource,
    NutritionCareProcessStatus,
    Person,
    PersonClinicalNote,
)
from ntk.pipelines.ncp import NutritionCareProcessPipeline
from ntk.pipelines.ncp.create import pipeline as ncp_pipeline
from ntk.repositories.person_repo import PersonClinicalRecords
from ntk.services.person.detail_builder import PersonDetailBuilder
from ntk.services.person.person_service import PersonService

if typing.TYPE_CHECKING:
    from ntk.models.ncp_context import BudgetedNCPContext
    from ntk.repositories.clinical_note_repo import ClinicalNoteRepo
    from ntk.repositories.embedding_repo import EmbeddingRepo
    from ntk.repositories.food_repo import FoodRepo
    from ntk.repositories.person_repo import PersonRepo
    from ntk.services.embedding_service import EmbeddingService
    from ntk.services.facility_resolver import FacilityResolver

_EXPECTED_WEIGHT_KG = 70


def test_generation_service_returns_person_nutrition_care_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    person = Person(id=1, name="Person")

    class PersonRepository:
        @staticmethod
        def get_by_identifier(
            person_identifier: str,
            *,
            facility_id: int | None = None,
        ) -> Person | None:
            assert person_identifier == "R-1"
            assert facility_id == 2  # noqa: PLR2004
            return person

        @staticmethod
        def get_by_id(person_id: int) -> Person | None:
            return person if person_id == person.id else None

        @staticmethod
        def get_clinical_records(_person_id: int) -> PersonClinicalRecords:
            return PersonClinicalRecords()

    class Agent:
        def __init__(self, **_kwargs: object) -> None:
            pass

        async def run(self, context: BudgetedNCPContext) -> str:
            assert context.additional_context == "wound healing"
            assert context.person.name == "Person"
            assert context.person.facility_name is None
            return "Generated assessment"

    class Resolver:
        @staticmethod
        def resolve(
            _name: str | None = None,
            *,
            facility_identifier: str | None = None,
        ) -> Facility:
            assert facility_identifier == "FAC-1"
            return Facility(
                id=2,
                facility_identifier=facility_identifier,
                name="Facility",
            )

    class ClinicalNoteRepository:
        @staticmethod
        def create_generated_draft(
            assessment: PersonClinicalNote,
        ) -> PersonClinicalNote:
            assessment.id = 1
            return assessment

    class Embedding:
        embedding_model = "embedding-model"

        @staticmethod
        def search_ncps(_query: str, *, top_k: int) -> list[object]:
            assert top_k == 5  # noqa: PLR2004
            return []

    monkeypatch.setattr(ncp_pipeline, "NutritionCareProcessAgent", Agent)
    assessment = asyncio.run(
        NutritionCareProcessPipeline(
            typing.cast("ClinicalNoteRepo", ClinicalNoteRepository()),
            person_service=PersonService(
                typing.cast("PersonRepo", PersonRepository()),
                typing.cast("FacilityResolver", Resolver()),
            ),
            embedding_repository=typing.cast("EmbeddingRepo", object()),
            food_repository=typing.cast("FoodRepo", object()),
            embedding_service=typing.cast("EmbeddingService", Embedding()),
        ).generate(
            "R-1",
            facility_identifier="FAC-1",
            context="wound healing",
        ),
    )

    assert assessment.person_id == person.id
    assert assessment.person is person
    assert assessment.ncp_source is NutritionCareProcessSource.GENERATED
    assert assessment.status is NutritionCareProcessStatus.DRAFT
    assert (
        assessment.content_hash
        == hashlib.sha256(
            b"Generated assessment",
        ).hexdigest()
    )


def test_generation_service_raises_for_unknown_person() -> None:
    class PersonRepository:
        @staticmethod
        def get_by_identifier(
            _person_identifier: str,
            *,
            facility_id: int | None = None,
        ) -> Person | None:
            assert facility_id is None
            return None

    service = NutritionCareProcessPipeline(
        typing.cast("ClinicalNoteRepo", object()),
        person_service=PersonService(typing.cast("PersonRepo", PersonRepository())),
        embedding_repository=typing.cast("EmbeddingRepo", object()),
    )

    with pytest.raises(LookupError, match="UNKNOWN"):
        asyncio.run(service.generate("UNKNOWN"))


def test_generation_pipeline_deduplicates_batch_requests() -> None:
    pipeline = NutritionCareProcessPipeline(
        typing.cast("ClinicalNoteRepo", object()),
    )
    calls: list[tuple[str, str | None, str | None]] = []

    async def generate(
        source_person_identifier: str,
        *,
        facility_identifier: str | None = None,
        context: str | None = None,
    ) -> PersonClinicalNote:
        calls.append((source_person_identifier, facility_identifier, context))
        return PersonClinicalNote(
            person_id=len(calls),
            note_date=date(2026, 9, 4),
            note_text="Assessment",
            raw_text="Assessment",
            note_key=f"ncp-{len(calls)}",
            content_hash=f"hash-{len(calls)}",
            created_by="model",
        )

    pipeline.generate = generate  # ty: ignore[invalid-assignment]
    results = asyncio.run(
        pipeline.generate_many(
            [
                SimpleNamespace(
                    source_person_identifier="R-1",
                    source_system="unknown",
                    facility_identifier="FAC-1",
                    context="first",
                ),
                SimpleNamespace(
                    source_person_identifier="R-1",
                    source_system="unknown",
                    facility_identifier="FAC-1",
                    context="duplicate",
                ),
                SimpleNamespace(
                    source_person_identifier="R-1",
                    source_system="unknown",
                    facility_identifier="FAC-2",
                    context="different facility",
                ),
            ],
        ),
    )

    assert calls == [
        ("R-1", "FAC-1", "first"),
        ("R-1", "FAC-2", "different facility"),
    ]
    assert len(results) == 2  # noqa: PLR2004


def test_person_detail_includes_direct_facility_identity() -> None:
    facility = Facility(id=2, facility_identifier="FAC", name="Facility")
    person = Person(
        id=1,
        name="Person",
        facility_id=2,
        facility=facility,
        person_identifier="R-1",
    )

    detail = PersonDetailBuilder().build(person, PersonClinicalRecords())

    assert detail.facility_id == 2  # noqa: PLR2004
    assert detail.person_identifier == "R-1"
    assert detail.facility is facility


def test_person_detail_contains_demographics_and_derived_age() -> None:
    birth_date = date(1946, 2, 1)
    person = Person(
        id=1,
        name="Person",
        date_of_birth=birth_date,
        sex="f",
        height_in=64.5,
    )

    detail = PersonDetailBuilder().build(
        person,
        PersonClinicalRecords(),
        on_date=date(2026, 9, 4),
    )

    assert detail.date_of_birth == birth_date
    assert detail.sex == "f"
    assert detail.height_in == 64.5  # noqa: PLR2004
    assert detail.age == 80  # noqa: PLR2004


def test_person_age_is_derived_from_date_of_birth() -> None:
    expected_before_birthday = 79
    expected_on_birthday = 80
    assert (
        PersonDetailBuilder._calculate_age(  # noqa: SLF001
            date(1946, 9, 1),
            date(2026, 8, 30),
        )
        == expected_before_birthday
    )
    assert (
        PersonDetailBuilder._calculate_age(  # noqa: SLF001
            date(1946, 8, 30),
            date(2026, 8, 30),
        )
        == expected_on_birthday
    )


def test_person_detail_exposes_deterministic_calculations() -> None:
    person = Person(
        id=1,
        name="Person",
        date_of_birth=date(1946, 9, 4),
        sex="female",
        height_in=64,
    )
    records = PersonClinicalRecords(
        weights=[
            PersonWeight(
                person_id=1,
                measured_at=datetime(2026, 6, 3, tzinfo=UTC),
                weight_lb=180,
            ),
            PersonWeight(
                person_id=1,
                measured_at=datetime(2026, 9, 1, tzinfo=UTC),
                weight_lb=154,
            ),
            PersonWeight(
                person_id=1,
                measured_at=datetime(2026, 8, 2, tzinfo=UTC),
                weight_lb=170,
            ),
        ],
    )

    detail = PersonDetailBuilder().build(
        person,
        records,
        on_date=date(2026, 9, 4),
    )
    calculations = detail.derived_calculations

    assert detail.age == 80  # noqa: PLR2004
    assert calculations.anthropometrics.current_weight_kg == _EXPECTED_WEIGHT_KG
    assert calculations.anthropometrics.current_weight_date == date(2026, 9, 1)
    assert [change.elapsed_days for change in calculations.weight_history] == [30, 90]
    assert all(change.direction == "loss" for change in calculations.weight_history)
    assert calculations.nutrition_needs.status == "computed"
    assert calculations.nutrition_needs.result is not None


def test_person_detail_orders_weights_and_reports_missing_needs_inputs() -> None:
    person = Person(id=1, name="Person", sex="unknown", height_in=64)
    records = PersonClinicalRecords(
        weights=[
            PersonWeight(
                person_id=1,
                measured_at=datetime(2026, 8, 1, tzinfo=UTC),
                weight_lb=150,
            ),
            PersonWeight(
                person_id=1,
                measured_at=datetime(2026, 9, 1, tzinfo=UTC),
                weight_lb=145,
            ),
        ],
    )

    detail = PersonDetailBuilder().build(person, records)

    assert [weight.weight_lb for weight in detail.weights] == [145, 150]
    assert detail.derived_calculations.anthropometrics.bmi is not None
    assert detail.derived_calculations.nutrition_needs.status == "not_computed"
    assert detail.derived_calculations.nutrition_needs.missing_inputs == [
        "normalized_sex",
        "age",
    ]
