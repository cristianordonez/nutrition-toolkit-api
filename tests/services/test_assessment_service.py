from __future__ import annotations

import asyncio
import hashlib
from datetime import UTC, date, datetime

import pytest

from ntk.models.sql.facility import Facility
from ntk.models.sql.resident import (
    AssessmentSource,
    Resident,
    ResidentAssessment,
    ResidentFacilityStay,
    StatusType,
)
from ntk.repositories.resident_repo import ResidentAssessmentRecords
from ntk.services.assessment import generation_service
from ntk.services.assessment.generation_service import (
    AssessmentGenerationService,
    _ResidentAgentContext,
)


def test_generation_service_returns_resident_assessment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resident = Resident(id=1, name="Resident")

    class ResidentRepository:
        @staticmethod
        def get_by_resident_identifier(
            resident_identifier: str,
            *,
            facility_id: str | None = None,
        ) -> Resident | None:
            assert resident_identifier == "R-1"
            assert facility_id == "FAC-1"
            return resident

        @staticmethod
        def get_assessment_records(_resident_id: int) -> ResidentAssessmentRecords:
            return ResidentAssessmentRecords(
                weights=[],
                labs=[],
                orders=[],
                progress_notes=[],
                wounds=[],
                edema=[],
                meal_intakes=[],
                clinical_facts=[],
            )

    class Agent:
        def __init__(self, **_kwargs: object) -> None:
            pass

        async def run(
            self,
            resident_context: _ResidentAgentContext,
            context: str | None = None,
        ) -> str:
            assert context == "wound healing"
            payload = resident_context.llm_payload()
            assert payload["resident_id"] == 1
            assert payload["resident_name"] == "Resident"
            assert "facility_name" not in payload
            assert "facility_resident_identifier" not in payload
            return "Generated assessment"

    class AssessmentRepository:
        embedding: object | None = None

        @staticmethod
        def create(assessment: ResidentAssessment) -> ResidentAssessment:
            assessment.id = 1
            return assessment

        @classmethod
        def get_embedding(cls, _assessment_id: int) -> object | None:
            return cls.embedding

        @classmethod
        def update(
            cls,
            assessment: ResidentAssessment,
            *,
            embedding: list[float],
            model_name: str,
        ) -> ResidentAssessment:
            assert embedding == [0.1]
            assert model_name == "embedding-model"
            cls.embedding = embedding
            return assessment

    class Embedding:
        def __init__(self, repository: object) -> None:
            assert repository == "embedding-repository"

    monkeypatch.setattr(generation_service, "AssessmentAgent", Agent)
    monkeypatch.setattr(generation_service, "EmbeddingService", Embedding)

    assessment = asyncio.run(
        AssessmentGenerationService(
            ResidentRepository(),  # ty: ignore[invalid-argument-type]
            AssessmentRepository(),  # ty: ignore[invalid-argument-type]
            "embedding-repository",  # ty: ignore[invalid-argument-type]
        ).generate(
            "R-1",
            facility_id="FAC-1",
            context="wound healing",
        ),
    )

    assert assessment.resident_id == resident.id
    assert assessment.resident is resident
    assert assessment.assessment_source is AssessmentSource.GENERATED
    assert assessment.status is StatusType.DRAFT
    assert (
        assessment.content_hash
        == hashlib.sha256(
            b"Generated assessment",
        ).hexdigest()
    )


def test_generation_service_raises_for_unknown_resident() -> None:
    class ResidentRepository:
        @staticmethod
        def get_by_resident_identifier(
            _resident_identifier: str,
            *,
            facility_id: str | None = None,
        ) -> Resident | None:
            assert facility_id is None
            return None

    service = AssessmentGenerationService(
        ResidentRepository(),  # ty: ignore[invalid-argument-type]
        object(),  # ty: ignore[invalid-argument-type]
        object(),  # ty: ignore[invalid-argument-type]
    )

    with pytest.raises(LookupError, match="UNKNOWN"):
        asyncio.run(service.generate("UNKNOWN"))


def test_resident_context_includes_current_stay_facility() -> None:
    facility_database_id = 2
    stay_id = 3
    facility = Facility(
        id=facility_database_id,
        facility_id="FAC",
        name="Facility",
    )
    stay = ResidentFacilityStay(
        id=stay_id,
        resident_id=1,
        facility_id=facility_database_id,
        facility_resident_identifier="R-1",
        admitted_at=datetime(2026, 1, 1, tzinfo=UTC),
        facility=facility,
    )
    resident = Resident(id=1, name="Resident", facility_stays=[stay])

    payload = _ResidentAgentContext(resident).llm_payload()

    assert payload["resident_facility_stay_id"] == stay_id
    assert payload["facility_id"] == facility_database_id
    assert payload["facility_resident_identifier"] == "R-1"
    assert payload["facility_name"] == "Facility"


def test_resident_context_contains_demographics_and_derived_age() -> None:
    date_of_birth = date(1946, 2, 1)
    height_in = 64.5
    resident = Resident(
        id=1,
        name="Resident",
        date_of_birth=date_of_birth,
        sex="f",
        height_in=height_in,
    )

    payload = _ResidentAgentContext(resident).llm_payload()

    assert payload["date_of_birth"] == date_of_birth
    assert payload["sex"] == "f"
    assert payload["height_in"] == height_in
    assert payload["age"] == _ResidentAgentContext._calculate_age(  # noqa: SLF001
        date_of_birth,
    )


def test_resident_age_is_derived_from_date_of_birth() -> None:
    expected_before_birthday = 79
    expected_on_birthday = 80
    assert (
        _ResidentAgentContext._calculate_age(  # noqa: SLF001
            date(1946, 9, 1),
            on_date=date(2026, 8, 30),
        )
        == expected_before_birthday
    )
    assert (
        _ResidentAgentContext._calculate_age(  # noqa: SLF001
            date(1946, 8, 30),
            on_date=date(2026, 8, 30),
        )
        == expected_on_birthday
    )
