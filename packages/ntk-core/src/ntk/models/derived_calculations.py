"""Deterministic calculation results shared by both apps.

Engine's calculators (nutrition, parenteral nutrition, tube-feed) produce
these result types locally, on-device, from documented person data. They
travel inside ``BudgetedPersonDetail.derived_calculations`` in the request
engine sends to cloud-api's NCP-generation endpoint, so cloud-api never
receives the raw patient records the calculations were derived from -- only
the already-computed numbers.
"""

# Pydantic resolves these annotation types at runtime when building model schemas.
# ruff: noqa: TC001, TC003

from __future__ import annotations

import typing
from datetime import date, datetime

from pydantic import BaseModel, Field

from ntk.calculators.nutrition_calculator import EnergyNeedsResult


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


class ExistingTubeFeedNutrition(BaseModel):
    """Deterministic daily nutrition provided by a documented feeding order."""

    formula_display_name: str
    feeding_method: str | None
    formula_volume_ml_day: float
    formula_kcal_day: int
    formula_protein_g_day: float
    formula_water_ml_day: float
    flush_water_ml_day: float
    total_water_ml_day: float


class TubeFeedCalculation(BaseModel):
    """Nutrition delivered by the selected current enteral-feeding order."""

    status: typing.Literal["computed", "not_computed", "not_applicable"]
    result: ExistingTubeFeedNutrition | None = None
    reason: str | None = None


class ParenteralNutritionCalculationResult(BaseModel):
    """Derived PN values; none of these fields are source documentation."""

    total_volume_ml: float | None
    rate_ml_hr: float | None
    hours_per_day: float | None
    dextrose_g_day: float | None
    amino_acid_g_day: float | None
    calculated_protein_g_day: float | None
    dextrose_kcal_day: float | None
    amino_acid_kcal_day: float | None
    lipid_g_day: float | None
    lipid_kcal_day: float | None
    total_kcal_day: float | None
    total_fluid_ml_day: float | None
    lipid_rate_ml_hr: float | None
    gir_mg_kg_min: float | None
    documented_protein_g: float | None
    documented_calories_kcal: float | None
    missing_inputs: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


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


__all__ = [
    "AnthropometricCalculations",
    "ClinicalConflict",
    "DerivedPersonCalculations",
    "ExistingTubeFeedNutrition",
    "NutritionNeedsCalculation",
    "ParenteralNutritionCalculation",
    "ParenteralNutritionCalculationResult",
    "TubeFeedCalculation",
    "WeightChangeDetail",
]
