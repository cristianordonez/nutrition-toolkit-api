"""Core temporal and validation conventions for normalized clinical domains."""

# ruff: noqa: PLR2004

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from ntk.models.extracted_fact_create import (
    AllergyPayload,
    AppetitePayload,
    DiagnosisPayload,
    DietPayload,
    FluidPlanPayload,
    FoodPreferencePayload,
    GIObservationPayload,
    MedicationPayload,
    NutritionGoalPayload,
    OralFeedingStatusPayload,
    ParenteralNutritionPayload,
)
from ntk.models.sql.clinical import (
    AppetiteLevel,
    ClinicalStatus,
    FoodPreferenceReason,
    FoodPreferenceType,
    FoodPreferenceValue,
    GISymptom,
    NutritionGoalType,
    ParenteralAccessRoute,
    PersonDiet,
    PersonMedication,
)


def test_created_at_is_application_time_not_historical_observation_time() -> None:
    observed_at = datetime(2020, 1, 1, tzinfo=UTC)
    before_create = datetime.now(UTC)

    medication = PersonMedication(
        person_id=1,
        name="Lasix",
        observed_at=observed_at,
        state_key="lasix",
        extracted_fact_id=1,
    )

    assert before_create <= medication.created_at <= datetime.now(UTC)
    assert medication.observed_at == observed_at
    assert medication.created_at != medication.observed_at


@pytest.mark.parametrize("status", list(ClinicalStatus))
def test_medication_payload_supports_every_lifecycle_status(
    status: ClinicalStatus,
) -> None:
    payload = MedicationPayload(name="Lasix", status=status)

    assert payload.status is status


def test_diagnosis_and_allergy_do_not_invent_optional_details() -> None:
    diagnosis = DiagnosisPayload(diagnosis="Type 2 diabetes mellitus")
    allergy = AllergyPayload(allergen="Shellfish")

    assert diagnosis.code is None
    assert diagnosis.code_system is None
    assert allergy.reaction is None


def test_food_avoidance_remains_a_preference_not_an_allergy() -> None:
    preference = FoodPreferencePayload(
        preference_type=FoodPreferenceType.DIETARY_PRACTICE,
        item="pork",
        preference=FoodPreferenceValue.AVOIDS,
        reason=FoodPreferenceReason.RELIGIOUS,
    )

    assert preference.type == "food_preference"
    assert preference.preference is FoodPreferenceValue.AVOIDS
    assert preference.reason is FoodPreferenceReason.RELIGIOUS


def test_new_payloads_preserve_distinct_nutrition_domains() -> None:
    appetite = AppetitePayload(appetite=AppetiteLevel.POOR)
    gi = GIObservationPayload(symptom=GISymptom.NAUSEA)
    oral = OralFeedingStatusPayload(
        swallowing_difficulty=True,
        slp_following=True,
    )
    goal = NutritionGoalPayload(goal_type=NutritionGoalType.WEIGHT_MAINTENANCE)

    assert appetite.type == "appetite"
    assert gi.type == "gi_observation"
    assert oral.type == "oral_feeding_status"
    assert goal.type == "nutrition_goal"


def test_parenteral_payload_does_not_calculate_documented_totals() -> None:
    payload = ParenteralNutritionPayload(
        access_route=ParenteralAccessRoute.CENTRAL,
        access_description="PICC",
        total_volume_ml=1800,
        hours_per_day=12,
        dextrose_g_per_l=200,
        amino_acid_g_per_l=50,
    )

    assert payload.documented_calories_kcal is None
    assert payload.documented_protein_g is None


def test_fluid_plan_requires_a_target_restriction_or_instruction() -> None:
    with pytest.raises(ValueError, match="requires a target"):
        FluidPlanPayload()

    assert FluidPlanPayload(restriction_ml_day=1500).restriction_ml_day == 1500


def test_diet_payload_canonicalizes_state_identity_values() -> None:
    payload = DietPayload(
        diet_type="Regular Diet",
        texture="Mechanical Soft",
        restrictions=["2 gm Na", "low-fat", "Low Fat"],
    )

    assert payload.diet_type == "regular"
    assert payload.texture == "mechanical_soft"
    assert payload.restrictions == ["2_g_sodium", "low_fat"]


def test_person_diet_model_canonicalizes_direct_input() -> None:
    diet = PersonDiet.model_validate(
        {
            "person_id": 1,
            "diet_type": "Regular Diet",
            "texture": "mechanical soft",
            "restrictions": ["low cholesterol"],
            "state_key": "test",
            "extracted_fact_id": 1,
        },
    )

    assert diet.diet_type == "regular"
    assert diet.texture == "mechanical_soft"
    assert diet.restrictions == ["low_cholesterol"]
