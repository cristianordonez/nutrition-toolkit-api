"""Table-less mirrors of engine's clinical SQLModel tables.

Also holds the shared NCP-generation wire contract between engine and
cloud-api. Engine's clinical records are SQLAlchemy-mapped tables
(``engine.models.sql.*``)
that cloud-api must never import directly -- cloud-api has no matching
database, and importing them would pull in table-registration machinery for
tables that don't exist in its process. These plain Pydantic mirrors carry the
same data fields (minus ``person``/``extracted_fact`` back-references) across
the wire instead. Engine converts its SQLModel instances into these DTOs with
``Model.model_validate(orm_instance)`` when assembling a generation request.
"""

# Pydantic resolves these annotation types at runtime when building model schemas.
# ruff: noqa: TC001, TC003

from __future__ import annotations

from datetime import date, datetime, time

from pydantic import BaseModel, ConfigDict, Field

from ntk.models.clinical_vocab import (
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
from ntk.models.derived_calculations import ClinicalConflict, DerivedPersonCalculations
from ntk.models.food_vocab import LiquidConsistency, PackageType


class _ClinicalRecordDTO(BaseModel):
    """Base for a table-less mirror of one clinical SQLModel record."""

    model_config = ConfigDict(from_attributes=True)

    id: int | None = None


class PersonWeight(_ClinicalRecordDTO):
    measured_at: datetime
    weight_lb: float
    description: str | None = None
    weight_context: WeightContext | None = None


class PersonDiet(_ClinicalRecordDTO):
    diet_type: str | None = None
    texture: str | None = None
    liquid_consistency: LiquidConsistency | None = None
    restrictions: list[str] = Field(default_factory=list)
    instructions: str | None = None
    status: ClinicalStatus = ClinicalStatus.UNKNOWN
    effective_at: datetime | None = None
    discontinued_at: datetime | None = None
    observed_at: datetime | None = None


class PersonEnteralFeeding(_ClinicalRecordDTO):
    formula: str | None = None
    route: str | None = None
    feeding_method: FeedingMethod | None = None
    rate_ml_hr: float | None = None
    hours_per_day: float | None = None
    bolus_volume_ml: float | None = None
    boluses_per_day: int | None = None
    flush_ml: float | None = None
    flush_frequency_hours: float | None = None
    flush_instructions: str | None = None
    feeding_schedule: str | None = None
    package_type: PackageType | None = None
    package_volume_ml: float | None = None
    caloric_density_kcal_ml: float | None = None
    instructions: str | None = None
    status: ClinicalStatus = ClinicalStatus.UNKNOWN
    effective_at: datetime | None = None
    discontinued_at: datetime | None = None
    observed_at: datetime | None = None


class PersonParenteralNutrition(_ClinicalRecordDTO):
    access_route: ParenteralAccessRoute | None = None
    access_description: str | None = None
    formula_type: ParenteralFormulaType | None = None
    total_volume_ml: float | None = None
    rate_ml_hr: float | None = None
    daily_start_time: time | None = None
    hours_per_day: float | None = None
    dextrose_g_per_l: float | None = None
    amino_acid_g_per_l: float | None = None
    documented_protein_g: float | None = None
    documented_calories_kcal: float | None = None
    lipid_delivery: LipidDeliveryType | None = None
    lipid_concentration_percent: float | None = None
    lipid_total_volume_ml: float | None = None
    lipid_run_time_hours: float | None = None
    lipid_rate_ml_hr: float | None = None
    instructions: str | None = None
    status: ParenteralNutritionStatus = ParenteralNutritionStatus.UNKNOWN
    effective_at: datetime | None = None
    discontinued_at: datetime | None = None
    observed_at: datetime | None = None


class PersonFluidPlan(_ClinicalRecordDTO):
    target_ml_day: float | None = None
    restriction_ml_day: float | None = None
    instructions: str | None = None
    status: ClinicalStatus = ClinicalStatus.UNKNOWN
    effective_at: datetime | None = None
    discontinued_at: datetime | None = None
    observed_at: datetime | None = None


class PersonDialysis(_ClinicalRecordDTO):
    dialysis_type: DialysisType | None = None
    schedule: str | None = None
    status: ClinicalStatus = ClinicalStatus.UNKNOWN
    effective_at: datetime | None = None
    discontinued_at: datetime | None = None
    observed_at: datetime | None = None


class PersonOralFeedingStatus(_ClinicalRecordDTO):
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


class PersonNutritionGoal(_ClinicalRecordDTO):
    goal_type: NutritionGoalType
    target_value: float | None = None
    target_unit: str | None = None
    target_date: date | None = None
    notes: str | None = None
    status: ClinicalStatus = ClinicalStatus.UNKNOWN
    effective_at: datetime | None = None
    discontinued_at: datetime | None = None
    observed_at: datetime | None = None


class PersonDiagnosis(_ClinicalRecordDTO):
    diagnosis: str
    code: str | None = None
    code_system: str | None = None
    status: ClinicalStatus = ClinicalStatus.UNKNOWN
    observed_at: datetime | None = None
    effective_at: datetime | None = None
    discontinued_at: datetime | None = None


class PersonAllergy(_ClinicalRecordDTO):
    allergen: str | None = None
    reaction: str | None = None
    no_known_allergies: bool = False
    status: ClinicalStatus = ClinicalStatus.UNKNOWN
    observed_at: datetime | None = None


class PersonMedication(_ClinicalRecordDTO):
    name: str
    dose: float | None = None
    dose_text: str | None = None
    dose_unit: str | None = None
    route: str | None = None
    frequency: str | None = None
    indication: str | None = None
    instructions: str | None = None
    status: ClinicalStatus = ClinicalStatus.UNKNOWN
    effective_at: datetime | None = None
    discontinued_at: datetime | None = None
    observed_at: datetime | None = None


class PersonSupplement(_ClinicalRecordDTO):
    product_name: str
    amount: float | None = None
    unit: str | None = None
    frequency: str | None = None
    route: str | None = None
    instructions: str | None = None
    status: ClinicalStatus = ClinicalStatus.UNKNOWN
    effective_at: datetime | None = None
    discontinued_at: datetime | None = None
    observed_at: datetime | None = None


class PersonFoodPreference(_ClinicalRecordDTO):
    preference_type: FoodPreferenceType
    item: str
    preference: FoodPreferenceValue
    reason: FoodPreferenceReason | None = None
    notes: str | None = None
    status: ClinicalStatus = ClinicalStatus.UNKNOWN
    observed_at: datetime | None = None


class PersonMiscOrder(_ClinicalRecordDTO):
    order_type: str | None = None
    description: str
    status: ClinicalStatus = ClinicalStatus.UNKNOWN
    effective_at: datetime | None = None
    discontinued_at: datetime | None = None
    observed_at: datetime | None = None


class PersonLab(_ClinicalRecordDTO):
    name: str
    result: str
    unit: str | None = None
    flag: str | None = None
    reference_range: str | None = None
    observed_at: datetime


class PersonEdema(_ClinicalRecordDTO):
    location: str
    severity: str | None = None
    observed_at: datetime


class PersonMealIntake(_ClinicalRecordDTO):
    min_percent: float | None = None
    max_percent: float | None = None
    observed_at: datetime


class PersonAppetiteObservation(_ClinicalRecordDTO):
    appetite: AppetiteLevel
    notes: str | None = None
    observed_at: datetime | None = None


class PersonGIObservation(_ClinicalRecordDTO):
    symptom: GISymptom
    severity: str | None = None
    notes: str | None = None
    observed_at: datetime | None = None


class PersonWound(_ClinicalRecordDTO):
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


class PersonClinicalFact(_ClinicalRecordDTO):
    clinical_fact_type: ClinicalFactType
    observation_type: str
    status: str | None = None
    severity: str | None = None
    description: str | None = None
    observed_at: datetime | None = None


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


class NCPGenerationRequest(BaseModel):
    """The request engine sends to cloud-api's NCP-generation endpoint."""

    model_config = ConfigDict(extra="forbid")

    person_identifier: str
    facility_identifier: str | None = None
    summary_text: str
    person: BudgetedPersonDetail
    additional_context: str | None = None


__all__ = [
    "BudgetedPersonDetail",
    "NCPGenerationRequest",
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
]
