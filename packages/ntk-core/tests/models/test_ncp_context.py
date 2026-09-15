from __future__ import annotations

from datetime import date

from ntk.models.derived_calculations import (
    AnthropometricCalculations,
    DerivedPersonCalculations,
    NutritionNeedsCalculation,
    ParenteralNutritionCalculation,
    TubeFeedCalculation,
)
from ntk.models.ncp_context import BudgetedPersonDetail, NCPGenerationRequest

EXPECTED_BMI = 23.9


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


def test_budgeted_person_detail_omits_raw_and_persistence_only_collections() -> None:
    fields = BudgetedPersonDetail.model_fields

    assert "person_id" not in fields
    assert "facility_id" not in fields
    assert "clinical_notes" not in fields
    assert "extracted_facts" not in fields
    assert "weight_history" in fields
    assert "recent_labs" in fields
    assert "recent_wounds" in fields


def test_ncp_generation_request_carries_the_wire_contract() -> None:
    request = NCPGenerationRequest(
        person_identifier="person-1",
        facility_identifier="facility-1",
        summary_text='{"name":"Doe, Jane"}',
        person=BudgetedPersonDetail(
            name="Doe, Jane",
            age=74,
            derived_calculations=_calculations(),
        ),
        additional_context="Focus on wound healing.",
    )

    payload = request.model_dump(mode="json")

    assert payload["person_identifier"] == "person-1"
    assert payload["person"]["name"] == "Doe, Jane"
    assert (
        payload["person"]["derived_calculations"]["anthropometrics"]["bmi"]
        == EXPECTED_BMI
    )
    assert payload["additional_context"] == "Focus on wound healing."
