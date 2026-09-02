from __future__ import annotations

import asyncio
import typing
from datetime import UTC, date, datetime
from types import SimpleNamespace

from ntk.models.sql.resident import (
    ClinicalFactType,
    Resident,
    ResidentAssessment,
    ResidentClinicalFact,
    ResidentWeight,
)
from ntk.presentation.api.routers import residents

if typing.TYPE_CHECKING:
    import pytest

    from ntk.controllers.residents.assessments import ResidentAssessmentsOptions
    from ntk.controllers.residents.clinical_facts import ResidentClinicalFactsOptions
    from ntk.controllers.residents.weights import ResidentWeightsOptions


def test_resident_routes_use_request_scoped_controllers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resident = Resident(
        id=1,
        resident_id="R-1",
        name="Resident",
        facility_id=1,
    )
    assessment = ResidentAssessment(
        resident_id=1,
        content="Assessment",
        content_hash="hash",
        assessment_date=date(2026, 8, 31),
        created_by="model",
    )
    weight = ResidentWeight(resident_id=1, weight_lb=150)
    fact = ResidentClinicalFact(
        resident_id=1,
        clinical_fact_type=ClinicalFactType.OBSERVATION,
        observation_type="appetite",
        observed_at=datetime(2026, 8, 31, tzinfo=UTC),
    )

    class ListController:
        def __init__(self, session: object) -> None:
            assert session == "session"

        @staticmethod
        def run(_options: object) -> object:
            return SimpleNamespace(result=SimpleNamespace(residents=[resident]))

    class AssessmentsController:
        def __init__(self, session: object) -> None:
            assert session == "session"

        @staticmethod
        def run(options: ResidentAssessmentsOptions) -> object:
            assert options.resident_ids == [resident.id]
            return SimpleNamespace(result=SimpleNamespace(assessments=[assessment]))

    class WeightsController:
        def __init__(self, session: object) -> None:
            assert session == "session"

        @staticmethod
        def run(options: ResidentWeightsOptions) -> object:
            assert options.resident_ids == [resident.id]
            return SimpleNamespace(result=SimpleNamespace(weights=[weight]))

    class FactsController:
        def __init__(self, session: object) -> None:
            assert session == "session"

        @staticmethod
        def run(options: ResidentClinicalFactsOptions) -> object:
            assert options.resident_ids == [resident.id]
            return SimpleNamespace(result=SimpleNamespace(clinical_facts=[fact]))

    monkeypatch.setattr(residents, "ResidentListController", ListController)
    monkeypatch.setattr(
        residents,
        "ResidentAssessmentsController",
        AssessmentsController,
    )
    monkeypatch.setattr(residents, "ResidentWeightsController", WeightsController)
    monkeypatch.setattr(
        residents,
        "ResidentClinicalFactsController",
        FactsController,
    )

    assert asyncio.run(residents.list_residents("session")) == [resident]  # ty: ignore[invalid-argument-type]
    assert asyncio.run(
        residents.get_resident_assessments(resident.id, "session"),  # ty: ignore[invalid-argument-type]
    ) == [assessment]
    assert asyncio.run(
        residents.get_resident_weights(resident.id, "session"),  # ty: ignore[invalid-argument-type]
    ) == [weight]
    assert asyncio.run(
        residents.get_resident_clinical_facts(resident.id, "session"),  # ty: ignore[invalid-argument-type]
    ) == [fact]
