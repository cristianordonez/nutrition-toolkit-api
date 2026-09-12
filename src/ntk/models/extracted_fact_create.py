"""Model used to created ExtractedFact."""

from __future__ import annotations

import typing
from datetime import date, datetime, time  # noqa: TC003
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ntk.models.sql.clinical.common import (
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
    normalize_diet_restriction,
    normalize_diet_texture,
    normalize_diet_type,
)
from ntk.models.sql.document import SourceAuthority
from ntk.models.sql.extracted_fact import ExtractionMethod
from ntk.models.sql.food import LiquidConsistency, PackageType  # noqa: TC001


class FactType(StrEnum):
    """Supported transient fact discriminators."""

    WEIGHT = "weight"
    LAB = "lab"
    EDEMA = "edema"
    WOUND = "wound"
    INTAKE = "intake"
    CLINICAL_FACT = "clinical_fact"
    MEDICATION = "medication"
    DIAGNOSIS = "diagnosis"
    ALLERGY = "allergy"
    DIET = "diet"
    ENTERAL_FEEDING = "enteral_feeding"
    PARENTERAL_NUTRITION = "parenteral_nutrition"
    SUPPLEMENT = "supplement"
    DIALYSIS = "dialysis"
    APPETITE = "appetite"
    FLUID_PLAN = "fluid_plan"
    GI_OBSERVATION = "gi_observation"
    ORAL_FEEDING_STATUS = "oral_feeding_status"
    FOOD_PREFERENCE = "food_preference"
    MISC_ORDER = "misc_order"
    NUTRITION_GOAL = "nutrition_goal"
    KNOWLEDGE_CHUNK = "knowledge_chunk"


class WeightPayload(BaseModel):
    type: typing.Literal["weight"] = "weight"
    weight_lb: float
    measured_at: datetime
    description: str | None = None
    weight_context: WeightContext | None = None


class LabPayload(BaseModel):
    type: typing.Literal["lab"] = "lab"
    name: str
    result: str
    unit: str | None = None
    reference_range: str | None = None
    flag: str | None = None
    observed_at: datetime


class EdemaPayload(BaseModel):
    type: typing.Literal["edema"] = "edema"
    location: str | None = None
    severity: str | None = None
    observed_at: datetime


class WoundPayload(BaseModel):
    type: typing.Literal["wound"] = "wound"
    wound_number: str | None = None
    wound_type: str
    location: str | None = None
    weeks_in_treatment: int | None = None
    progress: str | None = None
    stage: str | None = None
    size: str | None = None
    assessment_note: str | None = None
    physician_orders: str | None = None
    physician_orders_notes: str | None = None
    # May be supplied by a containing progress-note timestamp before persistence.
    observed_at: datetime | None = None


class MealIntakePayload(BaseModel):
    type: typing.Literal["intake"] = "intake"
    min_percent: float | None = None
    max_percent: float | None = None
    observed_at: datetime


class AppetitePayload(BaseModel):
    """A subjective appetite observation independent of meal consumption."""

    type: typing.Literal["appetite"] = "appetite"
    appetite: AppetiteLevel
    notes: str | None = None
    observed_at: datetime | None = None


class GIObservationPayload(BaseModel):
    """One nutrition-relevant gastrointestinal symptom observation."""

    type: typing.Literal["gi_observation"] = "gi_observation"
    symptom: GISymptom
    severity: str | None = None
    notes: str | None = None
    observed_at: datetime | None = None


class ClinicalFactPayload(BaseModel):
    """Narrative clinical observation or event without a dedicated table."""

    type: typing.Literal["clinical_fact"] = "clinical_fact"
    clinical_fact_type: typing.Literal["observation", "event"]
    observation_type: str
    status: str | None = None
    severity: str | None = None
    description: str | None = None
    observed_at: datetime | None = None


class _StatefulPayload(BaseModel):
    """Common optional lifecycle values supported by stateful source facts."""

    status: ClinicalStatus = ClinicalStatus.UNKNOWN
    observed_at: datetime | None = None
    effective_at: datetime | None = None
    discontinued_at: datetime | None = None
    instructions: str | None = None
    source_category: str | None = None
    source_revision_date: date | None = None


class MedicationPayload(_StatefulPayload):
    type: typing.Literal["medication"] = "medication"
    name: str
    dose: float | None = None
    dose_text: str | None = None
    dose_unit: str | None = None
    route: str | None = None
    frequency: str | None = None
    indication: str | None = None
    action: str | None = None


class DiagnosisPayload(_StatefulPayload):
    type: typing.Literal["diagnosis"] = "diagnosis"
    diagnosis: str
    code: str | None = None
    code_system: str | None = None


class AllergyPayload(BaseModel):
    type: typing.Literal["allergy"] = "allergy"
    allergen: str | None = None
    reaction: str | None = None
    no_known_allergies: bool = False
    status: ClinicalStatus = ClinicalStatus.UNKNOWN
    observed_at: datetime | None = None

    @model_validator(mode="after")
    def validate_subject(self) -> typing.Self:
        """Require either an allergen or an explicit no-known-allergies fact."""
        if bool(self.allergen) == self.no_known_allergies:
            message = "Provide exactly one of allergen or no_known_allergies=True"
            raise ValueError(message)
        return self


class DietPayload(_StatefulPayload):
    type: typing.Literal["diet"] = "diet"
    diet_type: str | None = None
    texture: str | None = None
    liquid_consistency: LiquidConsistency | None = None
    restrictions: list[str] = Field(default_factory=list)

    @field_validator("diet_type", mode="before")
    @classmethod
    def canonicalize_diet_type(cls, value: object) -> object:
        """Normalize source-equivalent diet labels before state-key creation."""
        return normalize_diet_type(value) if isinstance(value, str) else value

    @field_validator("texture", mode="before")
    @classmethod
    def canonicalize_texture(cls, value: object) -> object:
        """Normalize source-equivalent texture labels before state-key creation."""
        return normalize_diet_texture(value) if isinstance(value, str) else value

    @field_validator("restrictions", mode="before")
    @classmethod
    def canonicalize_restrictions(cls, value: object) -> object:
        """Normalize restriction labels and discard source duplicates."""
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


class EnteralFeedingPayload(_StatefulPayload):
    type: typing.Literal["enteral_feeding"] = "enteral_feeding"
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


class ParenteralNutritionPayload(BaseModel):
    """Source-documented PN prescription inputs; calculated totals are excluded."""

    type: typing.Literal["parenteral_nutrition"] = "parenteral_nutrition"
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
    source_category: str | None = None
    source_revision_date: date | None = None


class SupplementPayload(_StatefulPayload):
    type: typing.Literal["supplement"] = "supplement"
    product_name: str
    amount: float | None = Field(default=None, gt=0)
    unit: str | None = None
    frequency: str | None = None
    route: str | None = None


class DialysisPayload(_StatefulPayload):
    type: typing.Literal["dialysis"] = "dialysis"
    dialysis_type: DialysisType | None = None
    schedule: str | None = None


class OralFeedingStatusPayload(BaseModel):
    type: typing.Literal["oral_feeding_status"] = "oral_feeding_status"
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


class FoodPreferencePayload(BaseModel):
    type: typing.Literal["food_preference"] = "food_preference"
    preference_type: FoodPreferenceType
    item: str
    preference: FoodPreferenceValue
    reason: FoodPreferenceReason | None = None
    notes: str | None = None
    status: ClinicalStatus = ClinicalStatus.UNKNOWN
    observed_at: datetime | None = None


class MiscOrderPayload(_StatefulPayload):
    type: typing.Literal["misc_order"] = "misc_order"
    order_type: str | None = None
    description: str


class FluidPlanPayload(_StatefulPayload):
    """A documented overall fluid target or restriction."""

    type: typing.Literal["fluid_plan"] = "fluid_plan"
    target_ml_day: float | None = Field(default=None, ge=0)
    restriction_ml_day: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_plan(self) -> typing.Self:
        """Require structured fluid data or source instructions."""
        if (
            self.target_ml_day is None
            and self.restriction_ml_day is None
            and not (self.instructions or "").strip()
        ):
            message = "A fluid plan requires a target, restriction, or instructions"
            raise ValueError(message)
        return self


class NutritionGoalPayload(_StatefulPayload):
    type: typing.Literal["nutrition_goal"] = "nutrition_goal"
    goal_type: NutritionGoalType
    target_value: float | None = None
    target_unit: str | None = None
    target_date: date | None = None
    notes: str | None = None


class KnowledgeChunkPayload(BaseModel):
    type: typing.Literal["knowledge_chunk"] = "knowledge_chunk"
    content: str
    chunk_index: int
    knowledge_type: str


FactPayload = typing.Annotated[
    WeightPayload
    | LabPayload
    | EdemaPayload
    | WoundPayload
    | MealIntakePayload
    | AppetitePayload
    | GIObservationPayload
    | ClinicalFactPayload
    | MedicationPayload
    | DiagnosisPayload
    | AllergyPayload
    | DietPayload
    | EnteralFeedingPayload
    | ParenteralNutritionPayload
    | SupplementPayload
    | DialysisPayload
    | OralFeedingStatusPayload
    | FluidPlanPayload
    | FoodPreferencePayload
    | MiscOrderPayload
    | NutritionGoalPayload
    | KnowledgeChunkPayload,
    Field(discriminator="type"),
]


class ExtractedFactCreate(BaseModel):
    """Transient extracted fact used to create a persisted ExtractedFact."""

    model_config = ConfigDict(extra="forbid")

    payload: FactPayload
    confidence: float = Field(ge=0.0, le=1.0)
    confidence_reason: str | None = None
    model_name: str | None = None
    extraction_method: ExtractionMethod = ExtractionMethod.DETERMINISTIC
    # unresolved identity clues
    source_person_identifier: str | None = None
    source_person_name: str | None = None
    facility_name: str | None = None
    facility_identifier: str | None = None
    date_of_birth: date | None = None
    sex: str | None = None
    height_in: float | None = Field(default=None, gt=0)

    # already known identity
    person_id: int | None = None
    facility_id: int | None = None
    progress_note_id: int | None = None

    # source-system identity and authority
    source_system: str | None = None
    source_record_type: str | None = None
    source_record_id: str | None = None
    source_record_version: str | None = None
    source_document_id: str | None = None
    source_endpoint: str | None = None
    source_authority: SourceAuthority = SourceAuthority.UNKNOWN

    source_page: int | None = Field(default=None, ge=1)


__all__ = [
    "AllergyPayload",
    "AppetitePayload",
    "ClinicalFactPayload",
    "DiagnosisPayload",
    "DialysisPayload",
    "DietPayload",
    "EdemaPayload",
    "EnteralFeedingPayload",
    "ExtractedFactCreate",
    "FactPayload",
    "FactType",
    "FluidPlanPayload",
    "FoodPreferencePayload",
    "GIObservationPayload",
    "KnowledgeChunkPayload",
    "LabPayload",
    "MealIntakePayload",
    "MedicationPayload",
    "MiscOrderPayload",
    "NutritionGoalPayload",
    "OralFeedingStatusPayload",
    "ParenteralNutritionPayload",
    "SupplementPayload",
    "WeightPayload",
    "WoundPayload",
]
