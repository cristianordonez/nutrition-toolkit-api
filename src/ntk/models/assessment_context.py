"""Passive input models for assessment-agent generation."""

# Pydantic resolves these annotation types while constructing model schemas.
# ruff: noqa: TC001, TC003

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from ntk.models.person_detail import ClinicalConflict, DerivedPersonCalculations
from ntk.models.rag import RagSearchMatch
from ntk.models.sql import (
    PersonAllergy,
    PersonAppetiteObservation,
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
    PersonSupplement,
    PersonWeight,
    PersonWound,
)


class BudgetedPersonDetail(BaseModel):
    """Clinically relevant, bounded subset of a complete person detail."""

    model_config = ConfigDict(extra="forbid")

    name: str
    date_of_birth: date | None = None
    age: int | None = None
    sex: str | None = None
    height_in: float | None = None
    facility_name: str | None = None
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
    relevant_medications: list[PersonMedication] = Field(default_factory=list)
    active_supplements: list[PersonSupplement] = Field(default_factory=list)
    active_food_preferences: list[PersonFoodPreference] = Field(
        default_factory=list,
    )
    relevant_misc_orders: list[PersonMiscOrder] = Field(default_factory=list)
    weight_history: list[PersonWeight] = Field(default_factory=list)
    recent_labs: list[PersonLab] = Field(default_factory=list)
    recent_edema: list[PersonEdema] = Field(default_factory=list)
    recent_meal_intakes: list[PersonMealIntake] = Field(default_factory=list)
    recent_appetite_observations: list[PersonAppetiteObservation] = Field(
        default_factory=list,
    )
    recent_gi_observations: list[PersonGIObservation] = Field(
        default_factory=list,
    )
    recent_wounds: list[PersonWound] = Field(default_factory=list)
    recent_clinical_facts: list[PersonClinicalFact] = Field(default_factory=list)
    conflicts: list[ClinicalConflict] = Field(default_factory=list)
    derived_calculations: DerivedPersonCalculations


class BudgetedAssessmentContext(BaseModel):
    """Complete data payload prepared before invoking the assessment agent."""

    model_config = ConfigDict(extra="forbid")

    person: BudgetedPersonDetail
    relevant_assessments: list[RagSearchMatch] = Field(default_factory=list)
    additional_context: str | None = None


__all__ = ["BudgetedAssessmentContext", "BudgetedPersonDetail"]
