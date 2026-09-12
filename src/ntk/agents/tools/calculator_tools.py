"""Nutrition calculation tools."""

from __future__ import annotations

import typing
from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator
from pydantic_ai import FunctionToolset, RunContext

from ntk.models.sql.food import PackageType  # noqa: TC001 - Pydantic runtime type
from ntk.services.calculators import NutritionCalculator
from ntk.services.calculators.tubefeed_calculator import (
    BolusFeedingSchedule,
    ContinuousFeedingSchedule,
    ProteinSupplementContribution,
    TubeFeedCalculator,
)

if typing.TYPE_CHECKING:
    from ntk.repositories.food_repo import FoodRepo


@dataclass(frozen=True)
class CalculatorToolDependencies:
    """Runtime repositories required by calculation tools."""

    food_repo: FoodRepo


class TubeFeedDeliveryType(StrEnum):
    """Supported enteral-feeding delivery schedules."""

    CONTINUOUS = "continuous"
    BOLUS = "bolus"


class TubeFeedCalculationInput(BaseModel):
    """Documented inputs required for one complete tube-feed calculation."""

    formula: str = Field(
        description="Documented enteral formula name or product search text",
        min_length=1,
    )
    caloric_density_kcal_per_ml: float = Field(
        description="Documented formula caloric density in kcal/mL",
        gt=0,
    )
    package_type: PackageType = Field(description="Documented formula package type")
    package_volume_ml: int | None = Field(
        default=None,
        description="Documented package volume in mL when needed to identify a product",
        gt=0,
    )
    delivery_type: TubeFeedDeliveryType = Field(
        description="Documented or clinically selected continuous or bolus delivery",
    )
    energy_target_kcal_per_day: int = Field(
        description="Documented or deterministically calculated daily energy target",
        gt=0,
    )
    continuous_duration_hours: int | None = Field(
        default=None,
        description="Documented daily run time in hours for continuous feeding",
        gt=0,
        le=24,
    )
    n_bolus_feeds: int | None = Field(
        default=None,
        description="Documented or clinically selected number of daily bolus feeds",
        gt=0,
    )
    free_water_flush_target_ml_per_day: int | None = Field(
        default=None,
        description="Documented total daily free-water-flush target in mL",
        ge=0,
    )
    fluid_target_ml_per_day: float | None = Field(
        default=None,
        description=(
            "Documented or deterministically calculated total fluid target in mL/day"
        ),
        gt=0,
    )
    feeding_route: str = Field(
        default="PEG",
        description="Documented enteral access route",
        min_length=1,
    )
    start_time: str = Field(
        default="4pm",
        description="Documented hang time for continuous feeding",
        min_length=1,
    )
    protein_supplement: ProteinSupplementContribution | None = Field(
        default=None,
        description=(
            "Documented daily kcal, protein, and fluid from a protein supplement"
        ),
    )

    @model_validator(mode="after")
    def validate_schedule_and_fluids(self) -> typing.Self:
        """Require one complete delivery schedule and one fluid target."""
        if self.delivery_type is TubeFeedDeliveryType.CONTINUOUS:
            if self.continuous_duration_hours is None:
                message = "continuous_duration_hours is required for continuous feeding"
                raise ValueError(message)
            if self.n_bolus_feeds is not None:
                message = "n_bolus_feeds must be omitted for continuous feeding"
                raise ValueError(message)
        else:
            if self.n_bolus_feeds is None:
                message = "n_bolus_feeds is required for bolus feeding"
                raise ValueError(message)
            if self.continuous_duration_hours is not None:
                message = "continuous_duration_hours must be omitted for bolus feeding"
                raise ValueError(message)
        fluid_inputs = (
            self.free_water_flush_target_ml_per_day,
            self.fluid_target_ml_per_day,
        )
        if sum(value is not None for value in fluid_inputs) != 1:
            message = (
                "Provide exactly one of free_water_flush_target_ml_per_day or "
                "fluid_target_ml_per_day"
            )
            raise ValueError(message)
        return self


def calculate_tube_feed(
    ctx: RunContext[CalculatorToolDependencies],
    data: TubeFeedCalculationInput,
) -> dict[str, object]:
    """Calculate a complete enteral-feeding plan from documented inputs.

    Use only when formula name and density, package type, energy target, delivery
    schedule, and either a flush or total-fluid target are supplied. Formula lookup,
    rate, volume, nutrients, and flush totals are deterministic. If lookup returns
    multiple product choices, report those choices and do not guess.
    """
    if data.delivery_type is TubeFeedDeliveryType.BOLUS:
        if data.n_bolus_feeds is None:
            message = "Bolus schedule inputs were not narrowed"
            raise RuntimeError(message)
        schedule = BolusFeedingSchedule(
            n_bolus_feeds=data.n_bolus_feeds,
            feeding_route=data.feeding_route,
            protein_supplement=data.protein_supplement,
        )
    else:
        if data.continuous_duration_hours is None:
            message = "Continuous schedule inputs were not narrowed"
            raise RuntimeError(message)
        schedule = ContinuousFeedingSchedule(
            duration_hours=data.continuous_duration_hours,
            feeding_route=data.feeding_route,
            start_time=data.start_time,
            protein_supplement=data.protein_supplement,
        )
    result = TubeFeedCalculator(ctx.deps.food_repo).calculate(
        energy_needs=(
            data.energy_target_kcal_per_day,
            data.energy_target_kcal_per_day,
        ),
        formula=data.formula,
        package_type=data.package_type,
        package_volume_ml=data.package_volume_ml,
        caloric_density_kcal_per_ml=data.caloric_density_kcal_per_ml,
        fluid_target_ml_per_day=data.fluid_target_ml_per_day,
        free_water_flush_target_ml_per_day=data.free_water_flush_target_ml_per_day,
        schedule=schedule,
    )
    payload = result.model_dump(mode="json")
    payload["formatted_recommendation"] = result.to_console()
    return payload


CALCULATOR_TOOLSET = FunctionToolset[CalculatorToolDependencies](id="calculators")
CALCULATOR_TOOLSET.add_function(
    NutritionCalculator.calculate,
    name="calculate_nutrition_needs",
    description=(
        "Calculate a complete nutrition-needs profile only when current weight, "
        "height, age, and normalized equation sex are documented, the applicable "
        "result is not already in person.derived_calculations, and "
        "clinical evidence requires selecting factors. Supply the clinically "
        "selected factors; never multiply them yourself."
    ),
)
CALCULATOR_TOOLSET.add_function(
    calculate_tube_feed,
    name="calculate_tube_feed",
    description=(
        "Calculate formula lookup, delivery rate or bolus volume, nutrients, and "
        "flush totals only from a complete documented enteral-feeding input. "
        "Report ambiguous product choices and never guess."
    ),
)

__all__ = [
    "CALCULATOR_TOOLSET",
    "CalculatorToolDependencies",
    "TubeFeedCalculationInput",
    "TubeFeedDeliveryType",
    "calculate_tube_feed",
]
