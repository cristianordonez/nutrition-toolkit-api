from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from engine.models.person_detail import PersonDetail
from engine.models.sql.clinical import PersonWeight
from engine.pipelines.ncp.create.context_budgeter import ContextBudgeter
from ntk.models.derived_calculations import (
    AnthropometricCalculations,
    DerivedPersonCalculations,
    NutritionNeedsCalculation,
    ParenteralNutritionCalculation,
    TubeFeedCalculation,
)

_BUDGETED_WEIGHT_COUNT = 12
_MAX_PERCENT = 100


def _detail(*, weights: list[PersonWeight] | None = None) -> PersonDetail:
    return PersonDetail(
        person_id=7,
        person_identifier="R1",
        name="Doe, Jane",
        first_name="Jane",
        last_name="Doe",
        weights=weights or [],
        derived_calculations=DerivedPersonCalculations(
            calculated_on=date(2026, 9, 7),
            anthropometrics=AnthropometricCalculations(),
            nutrition_needs=NutritionNeedsCalculation(status="not_computed"),
            tube_feed=TubeFeedCalculation(status="not_applicable"),
            parenteral_nutrition=ParenteralNutritionCalculation(
                status="not_applicable",
            ),
        ),
    )


def test_budgeter_limits_history_and_reports_token_reduction() -> None:
    detail = _detail(
        weights=[
            PersonWeight(
                person_id=7,
                measured_at=datetime(2026, 9, 7, tzinfo=UTC) - timedelta(days=index),
                weight_lb=150 - index,
                description="Detailed clinical description " * 10,
            )
            for index in range(20)
        ],
    )

    budgeted = ContextBudgeter().budget(detail, facility_identifier="FAC-1")

    request = budgeted.request
    assert "person_id" not in type(request.person).model_fields
    assert request.person_identifier == "R1"
    assert request.facility_identifier == "FAC-1"
    assert request.person.current_diet is None
    assert len(request.person.weight_history) == _BUDGETED_WEIGHT_COUNT
    assert budgeted.omitted_record_counts == {"weight_history": 8}
    assert budgeted.raw_token_count > budgeted.final_token_count
    assert budgeted.tokens_removed == (
        budgeted.raw_token_count - budgeted.final_token_count
    )
    assert 0 < budgeted.token_reduction_percent <= _MAX_PERCENT


def test_budgeter_truncates_additional_context() -> None:
    detail = _detail()

    budgeted = ContextBudgeter().budget(
        detail,
        additional_context=" focus " * 2_000,
    )

    request = budgeted.request
    assert request.additional_context is not None
    assert request.additional_context.endswith("[truncated]")


def test_budgeter_requires_a_person_identifier() -> None:
    detail = _detail()
    detail.person_identifier = None

    with pytest.raises(ValueError, match="person identifier"):
        ContextBudgeter().budget(detail)
