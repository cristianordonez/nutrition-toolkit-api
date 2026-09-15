from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta

from engine.models.person_detail import PersonDetail
from engine.models.sql.clinical import PersonWeight
from ntk.models.derived_calculations import (
    AnthropometricCalculations,
    DerivedPersonCalculations,
    NutritionNeedsCalculation,
    ParenteralNutritionCalculation,
    TubeFeedCalculation,
)

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
    assert "clinical_notes" not in summary
    assert len(summary["recent_history"]["weights"]) == 6  # noqa: PLR2004
