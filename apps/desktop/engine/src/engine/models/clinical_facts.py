"""Typed, persistence-independent resident clinical fact models.

The SQLite ``clinical_fact`` table stores a generic envelope and JSON payload.
These Pydantic models are the application-facing representation of those
payloads.  They deliberately contain no SQLAlchemy mapping or relationships.
"""

from __future__ import annotations

import hashlib
import json
import typing
from datetime import UTC, date, datetime, time

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from engine.models.clinical_vocab import (
    AppetiteLevel,
    ClinicalFactType,
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
from engine.models.food_vocab import LiquidConsistency, PackageType  # noqa: TC001


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(UTC)


def normalize_clinical_text(value: str | None) -> str | None:
    """Normalize source text used in deterministic clinical identities."""
    if value is None:
        return None
    normalized = " ".join(value.split()).casefold()
    return normalized or None


def _normalize_diet_phrase(value: str) -> str:
    normalized = (
        value.casefold().replace("&", " and ").replace("_", " ").replace("-", " ")
    )
    return " ".join(normalized.split())


def normalize_diet_type(value: str | None) -> str | None:
    """Return a canonical diet-type token."""
    if value is None:
        return None
    normalized = _normalize_diet_phrase(value)
    if not normalized:
        return None
    aliases = {
        "regular diet": "regular",
        "renal diet": "renal",
        "cardiac diet": "cardiac",
        "consistent carbohydrate": "ccd",
        "consistent carbohydrate diet": "ccd",
        "controlled carbohydrate": "ccd",
        "carbohydrate controlled": "ccd",
        "diabetic": "ccd",
        "diabetic diet": "ccd",
        "no added salt": "nas",
        "no added salt diet": "nas",
    }
    return aliases.get(normalized, normalized.replace(" ", "_"))


def normalize_diet_texture(value: str | None) -> str | None:
    """Return a canonical food-texture token."""
    if value is None:
        return None
    normalized = _normalize_diet_phrase(value)
    if not normalized:
        return None
    aliases = {
        "mechanical soft": "mechanical_soft",
        "mech soft": "mechanical_soft",
        "puree": "pureed",
        "soft and bite sized": "soft_and_bite_sized",
        "minced and moist": "minced_and_moist",
        "easy to chew": "easy_to_chew",
    }
    return aliases.get(normalized, normalized.replace(" ", "_"))


def normalize_diet_restriction(value: str) -> str:
    """Return a canonical diet-restriction token."""
    normalized = _normalize_diet_phrase(value)
    aliases = {
        "2 g na": "2_g_sodium",
        "2 gm na": "2_g_sodium",
        "2 gram sodium": "2_g_sodium",
        "2 grams sodium": "2_g_sodium",
        "low fat": "low_fat",
        "low cholesterol": "low_cholesterol",
        "no added salt": "nas",
    }
    return aliases.get(normalized, normalized.replace(" ", "_"))


def build_state_key(*parts: typing.Any) -> str:  # noqa: ANN401
    """Return a stable hash for normalized clinical identity parts."""
    payload = json.dumps(parts, default=str, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


class ClinicalRecord(BaseModel):
    """Metadata common to hydrated clinical fact domain records."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: int | None = None
    person_id: int | None = None
    clinical_source_id: int | None = None
    created_at: datetime = Field(default_factory=utc_now)
    state_key: str | None = None
    observation_key: str | None = None


class PersonWeight(ClinicalRecord):
    measured_at: datetime
    weight_lb: float
    description: str | None = None
    weight_context: WeightContext | None = None


class PersonLab(ClinicalRecord):
    name: str
    result: str
    unit: str | None = None
    flag: str | None = None
    reference_range: str | None = None
    observed_at: datetime


class PersonEdema(ClinicalRecord):
    location: str
    severity: str | None = None
    observed_at: datetime


class PersonWound(ClinicalRecord):
    wound_number: str | None = None
    type: str
    location: str
    weeks_in_treatment: int | None = None
    progress: str | None = None
    stage: str | None = None
    size: str | None = None
    assessment_note: str | None = None
    physician_orders: str | None = None
    physician_orders_notes: str | None = None
    observed_at: datetime


class PersonMealIntake(ClinicalRecord):
    min_percent: float | None = None
    max_percent: float | None = None
    observed_at: datetime


class PersonAppetiteObservation(ClinicalRecord):
    appetite: AppetiteLevel
    notes: str | None = None
    observed_at: datetime | None = None


class PersonGIObservation(ClinicalRecord):
    symptom: GISymptom
    severity: str | None = None
    notes: str | None = None
    observed_at: datetime | None = None


class PersonClinicalFact(ClinicalRecord):
    """Narrative observation/event that has no more specific fact model."""

    clinical_fact_type: ClinicalFactType
    observation_type: str
    status: str | None = None
    severity: str | None = None
    description: str | None = None
    observed_at: datetime | None = None


class _StatefulClinicalRecord(ClinicalRecord):
    status: ClinicalStatus = ClinicalStatus.UNKNOWN
    observed_at: datetime | None = None
    effective_at: datetime | None = None
    discontinued_at: datetime | None = None
    instructions: str | None = None


class PersonMedication(_StatefulClinicalRecord):
    name: str
    dose: float | None = None
    dose_text: str | None = None
    dose_unit: str | None = None
    route: str | None = None
    frequency: str | None = None
    indication: str | None = None


class PersonDiagnosis(_StatefulClinicalRecord):
    diagnosis: str
    code: str | None = None
    code_system: str | None = None


class PersonAllergy(ClinicalRecord):
    allergen: str | None = None
    reaction: str | None = None
    no_known_allergies: bool = False
    status: ClinicalStatus = ClinicalStatus.UNKNOWN
    observed_at: datetime | None = None

    @model_validator(mode="after")
    def validate_subject(self) -> typing.Self:
        """Require an allergen or an explicit no-known-allergies assertion."""
        if bool(self.allergen) == self.no_known_allergies:
            msg = "Provide exactly one of allergen or no_known_allergies=True"
            raise ValueError(msg)
        return self


class PersonDiet(_StatefulClinicalRecord):
    diet_type: str | None = None
    texture: str | None = None
    liquid_consistency: LiquidConsistency | None = None
    restrictions: list[str] = Field(default_factory=list)

    @field_validator("diet_type", mode="before")
    @classmethod
    def canonicalize_diet_type(cls, value: object) -> object:
        """Normalize equivalent diet names before validation."""
        return normalize_diet_type(value) if isinstance(value, str) else value

    @field_validator("texture", mode="before")
    @classmethod
    def canonicalize_texture(cls, value: object) -> object:
        """Normalize equivalent texture names before validation."""
        return normalize_diet_texture(value) if isinstance(value, str) else value

    @field_validator("restrictions", mode="before")
    @classmethod
    def canonicalize_restrictions(cls, value: object) -> object:
        """Normalize and de-duplicate diet restriction names."""
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, (list, tuple, set)):
            return value
        normalized = [
            normalize_diet_restriction(item)
            for item in value
            if isinstance(item, str) and item.strip()
        ]
        return list(dict.fromkeys(normalized))


class PersonEnteralFeeding(_StatefulClinicalRecord):
    formula: str | None = None
    route: str | None = None
    feeding_method: FeedingMethod | None = None
    rate_ml_hr: float | None = Field(default=None, gt=0)
    hours_per_day: float | None = Field(default=None, gt=0, le=24)
    bolus_volume_ml: float | None = Field(default=None, gt=0)
    boluses_per_day: int | None = Field(default=None, gt=0)
    flush_ml: float | None = Field(default=None, ge=0)
    flush_frequency_hours: float | None = Field(default=None, gt=0)
    flush_instructions: str | None = None
    feeding_schedule: str | None = None
    package_type: PackageType | None = None
    package_volume_ml: float | None = Field(default=None, gt=0)
    caloric_density_kcal_ml: float | None = Field(default=None, gt=0)


class PersonParenteralNutrition(ClinicalRecord):
    access_route: ParenteralAccessRoute | None = None
    access_description: str | None = None
    formula_type: ParenteralFormulaType | None = None
    total_volume_ml: float | None = Field(default=None, gt=0)
    rate_ml_hr: float | None = Field(default=None, gt=0)
    daily_start_time: time | None = None
    hours_per_day: float | None = Field(default=None, gt=0, le=24)
    dextrose_g_per_l: float | None = Field(default=None, ge=0)
    amino_acid_g_per_l: float | None = Field(default=None, ge=0)
    documented_protein_g: float | None = Field(default=None, ge=0)
    documented_calories_kcal: float | None = Field(default=None, ge=0)
    lipid_delivery: LipidDeliveryType | None = None
    lipid_concentration_percent: float | None = Field(default=None, gt=0, le=100)
    lipid_total_volume_ml: float | None = Field(default=None, gt=0)
    lipid_run_time_hours: float | None = Field(default=None, gt=0, le=24)
    lipid_rate_ml_hr: float | None = Field(default=None, gt=0)
    instructions: str | None = None
    status: ParenteralNutritionStatus = ParenteralNutritionStatus.UNKNOWN
    observed_at: datetime | None = None
    effective_at: datetime | None = None
    discontinued_at: datetime | None = None


class PersonSupplement(_StatefulClinicalRecord):
    product_name: str
    amount: float | None = Field(default=None, gt=0)
    unit: str | None = None
    frequency: str | None = None
    route: str | None = None


class PersonDialysis(_StatefulClinicalRecord):
    dialysis_type: DialysisType | None = None
    schedule: str | None = None


class PersonOralFeedingStatus(ClinicalRecord):
    dentition_status: DentitionStatus | None = None
    upper_denture: DentureStatus | None = None
    lower_denture: DentureStatus | None = None
    chewing_difficulty: bool | None = None
    swallowing_difficulty: bool | None = None
    dysphagia: bool | None = None
    aspiration_risk: bool | None = None
    slp_following: bool | None = None
    notes: str | None = None
    status: ClinicalStatus = ClinicalStatus.UNKNOWN
    observed_at: datetime | None = None


class PersonFoodPreference(ClinicalRecord):
    preference_type: FoodPreferenceType
    item: str
    preference: FoodPreferenceValue
    reason: FoodPreferenceReason | None = None
    notes: str | None = None
    status: ClinicalStatus = ClinicalStatus.UNKNOWN
    observed_at: datetime | None = None


class PersonMiscOrder(_StatefulClinicalRecord):
    order_type: str | None = None
    description: str


class PersonFluidPlan(_StatefulClinicalRecord):
    target_ml_day: float | None = Field(default=None, ge=0)
    restriction_ml_day: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_plan(self) -> typing.Self:
        """Require at least one fluid target, restriction, or instruction."""
        if (
            self.target_ml_day is None
            and self.restriction_ml_day is None
            and not (self.instructions or "").strip()
        ):
            msg = "A fluid plan requires a target, restriction, or instructions"
            raise ValueError(msg)
        return self


class PersonNutritionGoal(_StatefulClinicalRecord):
    goal_type: NutritionGoalType
    target_value: float | None = None
    target_unit: str | None = None
    target_date: date | None = None
    notes: str | None = None


PersonClinicalRecord: typing.TypeAlias = (
    PersonAllergy
    | PersonAppetiteObservation
    | PersonClinicalFact
    | PersonDiagnosis
    | PersonDialysis
    | PersonDiet
    | PersonEdema
    | PersonEnteralFeeding
    | PersonFluidPlan
    | PersonFoodPreference
    | PersonGIObservation
    | PersonLab
    | PersonMealIntake
    | PersonMedication
    | PersonMiscOrder
    | PersonNutritionGoal
    | PersonOralFeedingStatus
    | PersonParenteralNutrition
    | PersonSupplement
    | PersonWeight
    | PersonWound
)


__all__ = [
    "ClinicalRecord",
    "PersonAllergy",
    "PersonAppetiteObservation",
    "PersonClinicalFact",
    "PersonClinicalRecord",
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
    "build_state_key",
    "normalize_clinical_text",
    "normalize_diet_restriction",
    "normalize_diet_texture",
    "normalize_diet_type",
    "utc_now",
]
