"""Energy Controller handles calculating all energy needs."""

from __future__ import annotations

import logging
import typing

from pydantic import BaseModel, Field

from ntk.controllers.base import BaseController
from ntk.models.base import ConsoleRenderableModel
from ntk.models.output import Output
from ntk.services.calculators import (
    EnergyNeedsInput,
    Gender,
    Goal,
    NutritionCalculator,
    RangeResult,
)

logger = logging.getLogger(__name__)


class EnergyOptions(BaseModel):
    """Settings for energy controller."""

    weight: float = Field(description="Weight in lbs")
    height: float = Field(description="Height in inches")
    age: int = Field(description="Age in years")
    goal: typing.Literal["lose", "maintain", "gain"] = Field(
        description="Goal for energy needs",
        default="maintain",
    )
    gender: typing.Literal["m", "f"] = Field(description="Gender", default="m")
    activity_level: float = Field(
        description="Activity level of person in scale from 1.2-1.9",
        default=1.2,
    )
    dialysis: bool = Field(description="If person is on hemodialysis", default=False)
    amputation: float | None = Field(
        description="Percentage of amputation. Hand=0.7 | Total leg=16.1 | Total Arm=4.9 | Foot=1.5 | Forearm and hand=2.3 | Calf and foot=5.8",  # noqa: E501
        default=None,
    )
    energy_needs: tuple[int, int] | None = Field(
        description="Manually set kcal range",
        default=None,
    )
    protein_needs: tuple[float, float] | None = Field(
        description="Manually set protein range",
        default=None,
    )


class EnergyResponse(ConsoleRenderableModel):
    bmi: float
    cbw: float
    mifflin: float
    ibw: float
    adjusted_ideal_body_weight: float
    bmi_adjusted_for_amputation: float | None = None
    ibw_adjusted_for_amputation: float | None = None
    bmi_category: str | None = None
    calculations_done_using: str | None = None
    calculation_weight: float
    weight_used_for_calculations_in_kg: float
    calorie_factor: tuple[int, int]
    protein_factor: tuple[float, float]
    fluid_factor: tuple[int, int]
    calories: tuple[int, int]
    protein: tuple[float, float]
    fluids: tuple[int, int]

    def to_console(self) -> str:
        """Format output for console.

        :return: formatted string
        """
        return (
            f"Energy Calculations:\n"
            f"  BMI: {self.bmi} ({self.bmi_category})\n"
            f"  CBW: {self.cbw}\n"
            f"  Mifflin: {self.mifflin}\n"
            f"  IBW: {self.ibw}\n"
            f"  Adjusted Ideal Body Weight: {self.adjusted_ideal_body_weight}\n"
            f"  Calculations Done Using: {self.calculations_done_using}\n"
            f"  Calculation Weight: {self.calculation_weight} ({self.weight_used_for_calculations_in_kg} kg)\n"  # noqa: E501
            f"  Calories: {self.calories[0]}-{self.calories[1]} kcal ({self.calorie_factor[0]}-{self.calorie_factor[1]} kcal/kg)\n"  # noqa: E501
            f"  Protein: {self.protein[0]}-{self.protein[1]} g ({self.protein_factor[0]}-{self.protein_factor[1]} g/kg)\n"  # noqa: E501
            f"  Fluids: {self.fluids[0]}-{self.fluids[1]} mL ({self.fluid_factor[0]}-{self.fluid_factor[1]} mL/kg)"  # noqa: E501
        )


class EnergyController(BaseController):
    """Controller for calculating energy needs."""

    name = "energy"
    help = "Calculate energy"
    options_model = EnergyOptions

    def run(self, options: EnergyOptions) -> Output:
        """Run Energy workflow.

        :param options: pydantic basemodel instance holding options
        :return: Output model
        """
        data = EnergyNeedsInput(
            height_in=options.height,
            weight_lb=options.weight,
            gender=Gender(options.gender),
            age=options.age,
            activity_level=options.activity_level,
            amputation_percent=options.amputation,
            goal=Goal(options.goal),
            dialysis=options.dialysis,
            protein_factor=options.protein_needs,
            calorie_factor=options.energy_needs,
        )
        calculated = NutritionCalculator.calculate(data)
        results = EnergyResponse(
            bmi=NutritionCalculator.calculate_bmi(options.weight, options.height),
            cbw=options.weight,
            mifflin=calculated.mifflin_kcal_day,
            ibw=calculated.ideal_weight_lb,
            adjusted_ideal_body_weight=calculated.adjusted_weight_lb,
            bmi_adjusted_for_amputation=(
                calculated.bmi if options.amputation is not None else None
            ),
            ibw_adjusted_for_amputation=(
                NutritionCalculator.calculate_ibw_adjusted_for_amputation(
                    data.gender,
                    data.height_in,
                    options.amputation,
                )
                if options.amputation is not None
                else None
            ),
            bmi_category=calculated.bmi_category,
            calculations_done_using=calculated.weight_basis,
            calculation_weight=calculated.calculation_weight_lb,
            weight_used_for_calculations_in_kg=calculated.calculation_weight_kg,
            calorie_factor=self._range_tuple(calculated.calorie_factor),
            protein_factor=self._range_tuple(calculated.protein_factor),
            fluid_factor=self._range_tuple(calculated.fluid_factor),
            calories=self._range_tuple(calculated.calories_kcal_day),
            protein=self._range_tuple(calculated.protein_g_day),
            fluids=self._range_tuple(calculated.fluids_ml_day),
        )
        return Output(result=results, controller=self.name, exit_code=0)

    @staticmethod
    def _range_tuple(result: RangeResult) -> tuple[float, float]:
        return result.low, result.high
