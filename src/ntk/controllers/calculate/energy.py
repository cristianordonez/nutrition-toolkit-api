"""Energy Controller handles calculating all energy needs."""

from __future__ import annotations

import logging
import typing

from pydantic import Field

from ntk.controllers.base import BaseController
from ntk.domain.calculator import Calculator
from ntk.domain.convert import Convert
from ntk.models.base import CustomBaseSettings
from ntk.models.output import Output

logger = logging.getLogger(__name__)


class EnergyOptions(CustomBaseSettings):
    """Settings for energy controller."""

    weight: float = Field(description="Weight in lbs")
    height: int = Field(description="Height in inches")
    age: int = Field(description="Age in years")
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


class EnergyController(BaseController):
    """Controller for calculating energy needs."""

    name = "energy"
    help = "Calculate energy"
    options_model = EnergyOptions

    def __init__(self) -> None:
        """Initialize EnergyController."""
        self.results = {}

    def run(self, options: EnergyOptions) -> Output:
        """Run Energy workflow.

        :param options: pydantic basemodel instance holding options
        :return: Output model
        """
        calc = Calculator(
            height=options.height,
            weight=options.weight,
            gender=options.gender,
            age=options.age,
            activity_level=options.activity_level,
            amputation=options.amputation,
        )
        self.results: dict[str, int | float | str] = {
            "BMI": calc.bmi,
            "CBW": options.weight,
            "Mifflin": calc.mifflin,
            "IBW": calc.ibw,
        }
        if options.amputation:
            self.results["BMI Adjusted for Amputation"] = (
                calc.bmi_adjusted_for_amputation
            )
            self.results["IBW Adjusted for Amputation"] = (
                calc.ibw_adjusted_for_amputation
            )
        energy_needs = options.energy_needs or (25, 30)
        protein_needs = self._get_protein_needs(options)
        calc_wt = self._get_calculation_wt(calc)
        calc_wt_in_kg = Convert.to_kg(calc_wt)
        kcal_range = calc.get_range(calc_wt_in_kg, energy_needs)
        protein_range = calc.get_range(calc_wt_in_kg, protein_needs)
        self.results["kcal"] = (
            f"{kcal_range[0]}-{kcal_range[1]} kcal ({energy_needs[0]}-{energy_needs[1]} kcal/kg)"  # noqa: E501
        )
        self.results["protein"] = (
            f"{protein_range[0]}-{protein_range[1]} g ({protein_needs[0]}-{protein_needs[1]} g/kg)"  # noqa: E501
        )
        self.results["fluid"] = (
            f"{kcal_range[0]}-{kcal_range[1]} mL ({energy_needs[0]}-{energy_needs[1]} mL/kg)"  # noqa: E501
        )
        return Output(result=self.results, controller=self.name, exit_code=0)

    @staticmethod
    def _get_protein_needs(options: EnergyOptions) -> tuple[float, float]:
        """Get protein needs for current run.

        :param options: EnergyOptions instance
        :return: range of protein needs
        """
        if options.protein_needs is not None:
            protein_needs = options.protein_needs
        elif options.dialysis:
            protein_needs = (1.2, 1.5)
        else:
            protein_needs = (1.0, 1.2)
        return protein_needs

    def _get_calculation_wt(self, calc: Calculator) -> float:
        weight_basis = calc.determine_weight_basis()
        calc_weight = calc.get_weight(weight_basis)
        msg = f"{weight_basis.value} ({calc_weight}#)"
        self.results["Calculations done using"] = msg
        return calc_weight
