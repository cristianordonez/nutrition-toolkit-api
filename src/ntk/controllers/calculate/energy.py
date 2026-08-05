"""Energy Controller handles calculating all energy needs."""

from __future__ import annotations

import logging
import typing

from pydantic import BaseModel, Field

from ntk.controllers.base import BaseController
from ntk.models.base import ConsoleRenderableModel
from ntk.models.output import Output
from ntk.services.calculator import CalculatorService

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
    dialysis: bool = Field(description="If patient is on hemodialysis", default=False)
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
        calc = self._create_calculator(options)
        results = self._build_base_results(calc, options)
        self._add_amputation_results(results, calc, options)
        self._add_estimated_needs(results, calc, options)
        return Output(result=results, controller=self.name, exit_code=0)

    @staticmethod
    def _create_calculator(options: EnergyOptions) -> CalculatorService:
        return CalculatorService(
            height=options.height,
            weight=options.weight,
            gender=options.gender,
            age=options.age,
            activity_level=options.activity_level,
            amputation=options.amputation,
            goal=options.goal,
        )

    @staticmethod
    def _build_base_results(
        calc: CalculatorService,
        options: EnergyOptions,
    ) -> EnergyResponse:
        return EnergyResponse(
            bmi=calc.bmi,
            cbw=options.weight,
            mifflin=calc.mifflin,
            ibw=calc.ibw,
            adjusted_ideal_body_weight=calc.aibw,
            calculation_weight=0.0,
            weight_used_for_calculations_in_kg=0,
            bmi_adjusted_for_amputation=None,
            ibw_adjusted_for_amputation=None,
            bmi_category=None,
            calculations_done_using=None,
            calorie_factor=(0, 0),
            protein_factor=(0, 0),
            fluid_factor=(0, 0),
            calories=(0, 0),
            protein=(0, 0),
            fluids=(0, 0),
        )

    @staticmethod
    def _add_amputation_results(
        results: EnergyResponse,
        calc: CalculatorService,
        options: EnergyOptions,
    ) -> None:
        if options.amputation:
            results.bmi_adjusted_for_amputation = calc.bmi_adjusted_for_amputation
            results.ibw_adjusted_for_amputation = calc.ibw_adjusted_for_amputation

    def _add_estimated_needs(
        self,
        results: EnergyResponse,
        calc: CalculatorService,
        options: EnergyOptions,
    ) -> None:
        goals = calc.get_goals(options.protein_needs, options.energy_needs)
        for key, value in goals.items():
            setattr(results, key, value)
