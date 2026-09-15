from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from api.models.ncp_context import BudgetedNCPContext
from api.models.rag import RagSearchMatch
from ntk.models.derived_calculations import (
    AnthropometricCalculations,
    DerivedPersonCalculations,
    NutritionNeedsCalculation,
    ParenteralNutritionCalculation,
    TubeFeedCalculation,
)
from ntk.models.ncp_context import BudgetedPersonDetail

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


def test_budgeted_ncp_context_has_explicit_agent_input_sections() -> None:
    context = BudgetedNCPContext(
        person=BudgetedPersonDetail(
            name="Doe, Jane",
            age=74,
            derived_calculations=_calculations(),
        ),
        relevant_ncps=[
            RagSearchMatch(
                document_id=EXPECTED_DOCUMENT_ID,
                filename="generated-ncp",
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
    assert payload["relevant_ncps"][0]["document_id"] == EXPECTED_DOCUMENT_ID
    assert payload["additional_context"] == "Focus on wound healing."


def test_budgeted_context_defaults_retrieval_and_runtime_context() -> None:
    context = BudgetedNCPContext(
        person=BudgetedPersonDetail(
            name="Doe, Jane",
            derived_calculations=_calculations(),
        ),
    )

    assert context.relevant_ncps == []
    assert context.additional_context is None


def test_budgeted_context_rejects_unplanned_top_level_sections() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        BudgetedNCPContext.model_validate(
            {
                "person": {
                    "name": "Doe, Jane",
                    "derived_calculations": _calculations(),
                },
                "retrieved_knowledge": [],
            },
        )
