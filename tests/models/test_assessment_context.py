from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta

import pytest
from pydantic import ValidationError

from ntk.models.assessment_context import (
    BudgetedAssessmentContext,
    BudgetedPersonDetail,
)
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

EXPECTED_BMI = 23.9
EXPECTED_DOCUMENT_ID = 31


def _calculations() -> DerivedPersonCalculations:
    return DerivedPersonCalculations(
        calculated_on=date(2026, 9, 8),
        anthropometrics=AnthropometricCalculations(
            current_weight_lb=148.2,
            bmi=EXPECTED_BMI,
        ),
        nutrition_needs=NutritionNeedsCalculation(status="not_computed"),
        tube_feed=TubeFeedCalculation(status="not_applicable"),
        parenteral_nutrition=ParenteralNutritionCalculation(
            status="not_applicable",
        ),
    )


def test_budgeted_assessment_context_has_explicit_agent_input_sections() -> None:
    context = BudgetedAssessmentContext(
        person=BudgetedPersonDetail(
            name="Doe, Jane",
            age=74,
            derived_calculations=_calculations(),
        ),
        relevant_assessments=[
            RagSearchMatch(
                document_id=EXPECTED_DOCUMENT_ID,
                filename="generated-assessment",
                chunk_text="Relevant finalized nutrition assessment.",
                similarity=0.91,
            ),
        ],
        additional_context="Focus on wound healing.",
    )

    payload = context.model_dump(mode="json")

    assert payload["person"]["name"] == "Doe, Jane"
    assert (
        payload["person"]["derived_calculations"]["anthropometrics"]["bmi"]
        == EXPECTED_BMI
    )
    assert payload["relevant_assessments"][0]["document_id"] == EXPECTED_DOCUMENT_ID
    assert payload["additional_context"] == "Focus on wound healing."


def test_budgeted_person_detail_omits_raw_and_persistence_only_collections() -> None:
    fields = BudgetedPersonDetail.model_fields

    assert "person_id" not in fields
    assert "facility_id" not in fields
    assert "progress_notes" not in fields
    assert "assessments" not in fields
    assert "extracted_facts" not in fields
    assert "weight_history" in fields
    assert "recent_labs" in fields
    assert "recent_wounds" in fields


def test_budgeted_context_defaults_retrieval_and_runtime_context() -> None:
    context = BudgetedAssessmentContext(
        person=BudgetedPersonDetail(
            name="Doe, Jane",
            derived_calculations=_calculations(),
        ),
    )

    assert context.relevant_assessments == []
    assert context.additional_context is None


def test_budgeted_context_rejects_unplanned_top_level_sections() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        BudgetedAssessmentContext.model_validate(
            {
                "person": {
                    "name": "Doe, Jane",
                    "derived_calculations": _calculations(),
                },
                "retrieved_knowledge": [],
            },
        )


def test_person_detail_creates_bounded_retrieval_summary() -> None:
    detail = PersonDetail(
        person_id=7,
        name="Doe, Jane",
        first_name="Jane",
        last_name="Doe",
        weights=[
            PersonWeight(
                person_id=7,
                measured_at=datetime(2026, 9, 7, tzinfo=UTC) - timedelta(days=index),
                weight_lb=150 - index,
            )
            for index in range(10)
        ],
        derived_calculations=_calculations(),
    )

    summary = json.loads(detail.create_summary_text())

    assert summary["name"] == "Doe, Jane"
    assert "person_id" not in summary
    assert "first_name" not in summary
    assert "assessments" not in summary
    assert "progress_notes" not in summary
    assert len(summary["recent_history"]["weights"]) == 6  # noqa: PLR2004
