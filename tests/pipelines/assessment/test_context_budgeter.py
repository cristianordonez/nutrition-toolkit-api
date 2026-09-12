from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from ntk.models.person_detail import (
    AnthropometricCalculations,
    DerivedPersonCalculations,
    NutritionNeedsCalculation,
    ParenteralNutritionCalculation,
    PersonDetail,
    TubeFeedCalculation,
)
from ntk.models.rag import RagSearchMatch
from ntk.models.sql.clinical import PersonWeight
from ntk.pipelines.assessment.create.context_budgeter import ContextBudgeter

_BUDGETED_ASSESSMENT_COUNT = 5
_BUDGETED_WEIGHT_COUNT = 12
_MAX_PERCENT = 100


def _detail(*, weights: list[PersonWeight] | None = None) -> PersonDetail:
    return PersonDetail(
        person_id=7,
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
                extracted_fact_id=index,
            )
            for index in range(20)
        ],
    )

    budgeted = ContextBudgeter().budget(detail)

    context = budgeted.assessment_context
    assert "person_id" not in type(context.person).model_fields
    assert context.person.current_diet is None
    assert len(context.person.weight_history) == _BUDGETED_WEIGHT_COUNT
    assert budgeted.omitted_record_counts == {"weight_history": 8}
    assert budgeted.raw_token_count > budgeted.final_token_count
    assert budgeted.tokens_removed == (
        budgeted.raw_token_count - budgeted.final_token_count
    )
    assert 0 < budgeted.token_reduction_percent <= _MAX_PERCENT


def test_budgeter_maps_and_limits_agent_context() -> None:
    detail = _detail()

    matches = [
        RagSearchMatch(
            document_id=index,
            filename=f"assessment-{index}.txt",
            chunk_text="example assessment " * 2_000,
            similarity=0.9,
        )
        for index in range(8)
    ]
    budgeted = ContextBudgeter().budget(
        detail,
        relevant_assessments=matches,
        additional_context=" focus " * 2_000,
    )

    context = budgeted.assessment_context
    assert len(context.relevant_assessments) == _BUDGETED_ASSESSMENT_COUNT
    assert context.relevant_assessments[0].chunk_text.endswith("[truncated]")
    assert context.additional_context is not None
    assert context.additional_context.endswith("[truncated]")
    assert budgeted.omitted_record_counts == {"relevant_assessments": 3}
