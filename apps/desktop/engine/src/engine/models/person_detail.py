"""Agent-facing person details and deterministic calculation results."""

# Pydantic resolves these annotation types at runtime when building model schemas.
# ruff: noqa: TC001, TC003

from __future__ import annotations

import json
import typing
from datetime import date

from pydantic import BaseModel, Field

from engine.models.sql import (
    ExtractedFact,
    Facility,
    PersonAllergy,
    PersonAppetiteObservation,
    PersonClinicalFact,
    PersonClinicalNote,
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
from ntk.models.derived_calculations import ClinicalConflict, DerivedPersonCalculations


class PersonDetail(BaseModel):
    """Complete person data used to prepare Nutrition Care Process context."""

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
    clinical_notes: list[PersonClinicalNote] = Field(default_factory=list)
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


__all__ = ["PersonDetail"]
