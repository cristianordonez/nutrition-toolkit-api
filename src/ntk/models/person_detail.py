"""Agent-facing person details and deterministic calculation results."""

# Pydantic resolves these annotation types at runtime when building model schemas.
# ruff: noqa: TC001, TC003

from __future__ import annotations

import json
import typing
from datetime import date, datetime

from pydantic import BaseModel, Field

from ntk.models.sql import (
    ExtractedFact,
    Facility,
    PersonAllergy,
    PersonAppetiteObservation,
    PersonAssessment,
    PersonClinicalFact,
    PersonDiagnosis,
    PersonDialysis,
    PersonDiet,
    PersonEdema,
    PersonEnteralFeeding,
    PersonFluidPlan,
    PersonFoodPreference,
    PersonGIObservation,
    PersonLab,
    PersonMealIntake,
    PersonMedication,
    PersonMiscOrder,
    PersonNutritionGoal,
    PersonOralFeedingStatus,
    PersonParenteralNutrition,
    PersonProgressNote,
    PersonSupplement,
    PersonWeight,
    PersonWound,
)
from ntk.services.calculators.nutrition_calculator import EnergyNeedsResult
from ntk.services.calculators.parenteral_nutrition_calculator import (
    ParenteralNutritionCalculationResult,
)
from ntk.services.calculators.tubefeed_calculator import ExistingTubeFeedNutrition


class ClinicalConflict(BaseModel):
    """An unresolved current-state conflict that the agent must see."""

    concept: str
    message: str
    record_ids: tuple[int, ...] = ()


class WeightChangeDetail(BaseModel):
    """A deterministic comparison between the latest and a prior weight."""

    current_measured_at: datetime
    latest_weight_lb: float
    prior_measured_at: datetime
    prior_weight_lb: float
    change_lb: float
    absolute_change_lb: float
    percent_change: float
    direction: typing.Literal["loss", "gain", "stable"]
    elapsed_days: int
    elapsed_timeframe: str = Field(
        description=(
            "Calendar-based duration from the prior weight to the latest weight, "
            "rounded to whole months or expressed as less than one month"
        ),
    )
    significance_interval: typing.Literal["1 month", "3 months", "6 months"] | None = (
        Field(
            description=(
                "Clinical significance threshold window selected from elapsed days; "
                "this is not the exact elapsed duration and must not be printed as one"
            ),
        )
    )
    significance_threshold_percent: float | None
    clinically_significant: bool
    comparison_text: str = Field(
        description="Deterministic prior-to-latest comparison, ready to print verbatim",
    )


class AnthropometricCalculations(BaseModel):
    """Deterministic measurements derived from documented demographics."""

    current_weight_lb: float | None = None
    current_weight_date: date | None = None
    current_weight_kg: float | None = None
    bmi: float | None = None
    bmi_category: str | None = None
    ideal_weight_lb: float | None = None
    adjusted_ideal_weight_lb: float | None = None
    mifflin_kcal_day: float | None = None
    amputation_percent: float | None = None
    missing_inputs: list[str] = Field(default_factory=list)


class NutritionNeedsCalculation(BaseModel):
    """A computed needs profile or the documented reason it was unavailable."""

    status: typing.Literal["computed", "not_computed"]
    result: EnergyNeedsResult | None = None
    goal: str | None = None
    dialysis: bool | None = None
    factor_review_required: bool = True
    missing_inputs: list[str] = Field(default_factory=list)
    reason: str | None = None


class TubeFeedCalculation(BaseModel):
    """Nutrition delivered by the selected current enteral-feeding order."""

    status: typing.Literal["computed", "not_computed", "not_applicable"]
    result: ExistingTubeFeedNutrition | None = None
    reason: str | None = None


class ParenteralNutritionCalculation(BaseModel):
    """Nutrition delivered by the selected current parenteral prescription."""

    status: typing.Literal["computed", "not_computed", "not_applicable"]
    result: ParenteralNutritionCalculationResult | None = None
    reason: str | None = None


class DerivedPersonCalculations(BaseModel):
    """All deterministic values prepared before the person reaches the agent."""

    calculated_on: date
    anthropometrics: AnthropometricCalculations
    weight_history: list[WeightChangeDetail] = Field(default_factory=list)
    nutrition_needs: NutritionNeedsCalculation
    tube_feed: TubeFeedCalculation
    parenteral_nutrition: ParenteralNutritionCalculation


class PersonDetail(BaseModel):
    """Complete person data used to prepare assessment-generation context."""

    _SUMMARY_CURRENT_FIELDS: typing.ClassVar[tuple[str, ...]] = (
        "name",
        "age",
        "sex",
        "height_in",
        "current_weight",
        "current_diet",
        "current_enteral_feeding",
        "current_parenteral_nutrition",
        "current_fluid_plan",
        "current_dialysis",
        "current_oral_feeding_status",
        "current_weight_goal",
        "active_nutrition_goals",
        "active_diagnoses",
        "active_allergies",
        "active_medications",
        "active_supplements",
        "active_food_preferences",
        "active_misc_orders",
        "conflicts",
        "derived_calculations",
    )
    _SUMMARY_HISTORY_LIMITS: typing.ClassVar[dict[str, int]] = {
        "weights": 6,
        "labs": 10,
        "edema": 3,
        "meal_intakes": 5,
        "appetite_observations": 5,
        "gi_observations": 5,
        "wounds": 5,
        "clinical_facts": 5,
    }

    person_id: int | None = None
    name: str
    first_name: str
    last_name: str
    date_of_birth: date | None = None
    age: int | None = None
    sex: str | None = None
    height_in: float | None = None
    facility_id: int | None = None
    facility: Facility | None = None
    person_identifier: str | None = None

    current_weight: PersonWeight | None = None
    current_diet: PersonDiet | None = None
    current_enteral_feeding: PersonEnteralFeeding | None = None
    current_parenteral_nutrition: PersonParenteralNutrition | None = None
    current_fluid_plan: PersonFluidPlan | None = None
    current_dialysis: PersonDialysis | None = None
    current_oral_feeding_status: PersonOralFeedingStatus | None = None
    current_weight_goal: PersonNutritionGoal | None = None

    active_nutrition_goals: list[PersonNutritionGoal] = Field(default_factory=list)
    active_diagnoses: list[PersonDiagnosis] = Field(default_factory=list)
    active_allergies: list[PersonAllergy] = Field(default_factory=list)
    active_medications: list[PersonMedication] = Field(default_factory=list)
    active_supplements: list[PersonSupplement] = Field(default_factory=list)
    active_food_preferences: list[PersonFoodPreference] = Field(default_factory=list)
    active_misc_orders: list[PersonMiscOrder] = Field(default_factory=list)

    weights: list[PersonWeight] = Field(default_factory=list)
    labs: list[PersonLab] = Field(default_factory=list)
    diagnoses: list[PersonDiagnosis] = Field(default_factory=list)
    allergies: list[PersonAllergy] = Field(default_factory=list)
    medications: list[PersonMedication] = Field(default_factory=list)
    diets: list[PersonDiet] = Field(default_factory=list)
    enteral_feedings: list[PersonEnteralFeeding] = Field(default_factory=list)
    parenteral_nutrition_records: list[PersonParenteralNutrition] = Field(
        default_factory=list,
    )
    fluid_plans: list[PersonFluidPlan] = Field(default_factory=list)
    supplements: list[PersonSupplement] = Field(default_factory=list)
    dialysis_records: list[PersonDialysis] = Field(default_factory=list)
    oral_feeding_status_history: list[PersonOralFeedingStatus] = Field(
        default_factory=list,
    )
    food_preferences: list[PersonFoodPreference] = Field(default_factory=list)
    misc_orders: list[PersonMiscOrder] = Field(default_factory=list)
    nutrition_goals: list[PersonNutritionGoal] = Field(default_factory=list)
    edema: list[PersonEdema] = Field(default_factory=list)
    meal_intakes: list[PersonMealIntake] = Field(default_factory=list)
    appetite_observations: list[PersonAppetiteObservation] = Field(
        default_factory=list,
    )
    gi_observations: list[PersonGIObservation] = Field(default_factory=list)
    wounds: list[PersonWound] = Field(default_factory=list)
    clinical_facts: list[PersonClinicalFact] = Field(default_factory=list)
    progress_notes: list[PersonProgressNote] = Field(default_factory=list)
    assessments: list[PersonAssessment] = Field(default_factory=list)
    extracted_facts: list[ExtractedFact] = Field(default_factory=list)

    conflicts: list[ClinicalConflict] = Field(default_factory=list)
    derived_calculations: DerivedPersonCalculations

    def create_summary_text(self) -> str:
        """Return a bounded clinical summary suitable for similarity search."""
        values = self.model_dump(mode="json", exclude_none=True)
        summary = {
            name: values[name]
            for name in self._SUMMARY_CURRENT_FIELDS
            if values.get(name) not in (None, [], {})
        }
        recent_history = {
            name: records[:limit]
            for name, limit in self._SUMMARY_HISTORY_LIMITS.items()
            if isinstance((records := values.get(name)), list) and records
        }
        if recent_history:
            summary["recent_history"] = recent_history
        return json.dumps(summary, separators=(",", ":"), sort_keys=True)


__all__ = [
    "AnthropometricCalculations",
    "ClinicalConflict",
    "DerivedPersonCalculations",
    "NutritionNeedsCalculation",
    "ParenteralNutritionCalculation",
    "PersonDetail",
    "TubeFeedCalculation",
    "WeightChangeDetail",
]
