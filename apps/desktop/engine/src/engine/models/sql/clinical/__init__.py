"""Canonical person clinical domain models.

Weights and labs are deterministic-first because their source reports have
stable structure. Edema, meal intake, and wounds may also be populated
from typed AI payloads. PersonClinicalFact is the narrative fallback for
observations and events without a dedicated domain model.
"""

from __future__ import annotations

from .allergy import PersonAllergy
from .appetite import PersonAppetiteObservation
from .clinical_fact import ClinicalFactType, PersonClinicalFact
from .common import (
    AppetiteLevel,
    ClinicalStatus,
    DentitionStatus,
    DentureStatus,
    DialysisType,
    FeedingMethod,
    FoodPreferenceReason,
    FoodPreferenceType,
    FoodPreferenceValue,
    GISymptom,
    LipidDeliveryType,
    NutritionGoalType,
    ParenteralAccessRoute,
    ParenteralFormulaType,
    ParenteralNutritionStatus,
    WeightContext,
)
from .diagnosis import PersonDiagnosis
from .dialysis import PersonDialysis
from .diet import PersonDiet
from .edema import PersonEdema
from .enteral_feeding import PersonEnteralFeeding
from .fluid_plan import PersonFluidPlan
from .food_preference import PersonFoodPreference
from .gi_observation import PersonGIObservation
from .lab import PersonLab
from .meal_intake import PersonMealIntake
from .medication import PersonMedication
from .misc_order import PersonMiscOrder
from .nutrition_goal import PersonNutritionGoal
from .oral_feeding_status import PersonOralFeedingStatus
from .parenteral_nutrition import PersonParenteralNutrition
from .supplement import PersonSupplement
from .weight import PersonWeight
from .wound import PersonWound

DETERMINISTIC_FIRST_MODELS = (PersonWeight, PersonLab)
AI_CAPABLE_STRUCTURED_MODELS = (
    PersonAllergy,
    PersonAppetiteObservation,
    PersonDiagnosis,
    PersonDialysis,
    PersonDiet,
    PersonEdema,
    PersonEnteralFeeding,
    PersonFoodPreference,
    PersonFluidPlan,
    PersonGIObservation,
    PersonMealIntake,
    PersonMedication,
    PersonOralFeedingStatus,
    PersonParenteralNutrition,
    PersonSupplement,
    PersonNutritionGoal,
    PersonWound,
)

__all__ = [
    "AI_CAPABLE_STRUCTURED_MODELS",
    "DETERMINISTIC_FIRST_MODELS",
    "AppetiteLevel",
    "ClinicalFactType",
    "ClinicalStatus",
    "DentitionStatus",
    "DentureStatus",
    "DialysisType",
    "FeedingMethod",
    "FoodPreferenceReason",
    "FoodPreferenceType",
    "FoodPreferenceValue",
    "GISymptom",
    "LipidDeliveryType",
    "NutritionGoalType",
    "ParenteralAccessRoute",
    "ParenteralFormulaType",
    "ParenteralNutritionStatus",
    "PersonAllergy",
    "PersonAppetiteObservation",
    "PersonClinicalFact",
    "PersonDiagnosis",
    "PersonDialysis",
    "PersonDiet",
    "PersonEdema",
    "PersonEnteralFeeding",
    "PersonFluidPlan",
    "PersonFoodPreference",
    "PersonGIObservation",
    "PersonLab",
    "PersonMealIntake",
    "PersonMedication",
    "PersonMiscOrder",
    "PersonNutritionGoal",
    "PersonOralFeedingStatus",
    "PersonParenteralNutrition",
    "PersonSupplement",
    "PersonWeight",
    "PersonWound",
    "WeightContext",
]
