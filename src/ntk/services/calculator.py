from __future__ import annotations

import logging
import typing
from enum import Enum

from ntk.utils.convert import Convert

logger = logging.getLogger(__name__)

MIN_HEIGHT = 60.0

GERIATRIC_AGE = 70


class BMICategory(Enum):
    UNDERWEIGHT = "Underweight"
    NORMAL = "Normal"
    OVERWEIGHT = "Overweight"
    OBESE = "Obese"
    MORBIDLY_OBESE = "Morbidly Obese"


STANDARD_BMI_RANGES = {
    BMICategory.UNDERWEIGHT: (0.0, 18.5),
    BMICategory.NORMAL: (18.5, 25.0),
    BMICategory.OVERWEIGHT: (25.0, 30.0),
    BMICategory.OBESE: (30.0, 40.0),
    BMICategory.MORBIDLY_OBESE: (40.0, float("inf")),
}

GERIATRIC_BMI_RANGES = {
    BMICategory.UNDERWEIGHT: (0.0, 23.0),
    BMICategory.NORMAL: (23.0, 28.0),
    BMICategory.OVERWEIGHT: (28.0, 30.0),
    BMICategory.OBESE: (30.0, 40.0),
    BMICategory.MORBIDLY_OBESE: (40.0, float("inf")),
}


def get_bmi_category(
    bmi: float,
    ranges: dict[BMICategory, tuple[float, float]],
) -> BMICategory:
    """Get BMI category based on BMI and age.

    :param bmi: Calculated BMI float
    :param ranges: Dictionary of BMI ranges
    :return: BMICategory enum value
    """
    for range_category, (lower, upper) in ranges.items():
        if lower <= bmi < upper:
            return range_category
    msg = f"Invalid BMI: {bmi}"
    raise ValueError(msg)


class WeightBasis(Enum):
    """Weight to use for calculations."""

    CBW = "Current Body Weight"
    IBW = "Ideal Body Weight"
    AIBW = "Ideal Body Weight Adjusted for Obesity"


class CalculatorService:
    """Handles nutrition calculations."""

    def __init__(  # noqa: PLR0913
        self,
        height: float,
        weight: float,
        gender: typing.Literal["m", "f"],
        age: int,
        activity_level: float = 1.2,
        amputation: float | None = None,
        goal: typing.Literal["lose", "maintain", "gain"] = "maintain",
        *,
        dialysis: bool = False,
    ) -> None:
        """Initialize calculator class.

        :param height: height in inches
        :param weight: weight in lbs
        :param gender: users gender, m or f
        :param age: age in years
        :param activity_level: how active user is, usually 1 - 1.9
        :param amputation: percentage of limb removed or none
        :param goal: desired outcome for energy needs
        :param dialysis: if user is on dialysis
        """
        self.height = height
        self.weight = weight
        self.gender = gender
        self.age = age
        self.activity_level = activity_level
        self.amputation = amputation
        self.goal = goal
        self.dialysis = dialysis

    def get_goals(
        self,
        protein_needs: tuple[float, float] | None = None,
        energy_needs: tuple[int, int] | None = None,
    ) -> dict[str, tuple[int | float, int | float] | str | int | float]:
        """Get nutrition goals based on weight and activity level.

        :return: dict of nutrition goals
        """
        bmi_category = self._determine_bmi_category()
        weight_basis = self._determine_weight_basis(bmi_category)
        weight = self.get_weight(weight_basis)
        calc_wt_in_kg = Convert.to_kg(weight)
        protein_factor = self._get_protein_needs(
            protein_needs,
            dialysis=self.dialysis,
        )
        energy_factor = self._get_energy_needs(energy_needs)
        return {
            "bmi_category": bmi_category.name,
            "calculations_done_using": weight_basis.value,
            "calculation_weight": weight,
            "weight_used_for_calculations_in_kg": calc_wt_in_kg,
            "calorie_factor": energy_factor,
            "protein_factor": protein_factor,
            "fluid_factor": energy_factor,
            "calories": self.get_range(calc_wt_in_kg, energy_factor),
            "fluids": self.get_range(calc_wt_in_kg, energy_factor),
            "protein": self.get_range(calc_wt_in_kg, protein_factor),
        }

    def _get_energy_needs(
        self,
        energy_needs: tuple[int, int] | None = None,
    ) -> tuple[int, int]:
        """Get energy needs for current run.

        :return: range of kcal needs
        """
        if energy_needs is not None:
            return energy_needs
        if self.goal == "lose":
            return (20, 25)
        if self.goal == "gain":
            return (30, 35)
        return (25, 30)

    @staticmethod
    def _get_protein_needs(
        protein_needs: tuple[float, float] | None = None,
        *,
        dialysis: bool = False,
    ) -> tuple[float, float]:
        """Get protein needs for current run.

        :param options: EnergyOptions instance
        :return: range of protein needs
        """
        if protein_needs is not None:
            return protein_needs
        if dialysis:
            return (1.2, 1.5)
        return (1.0, 1.2)

    @property
    def mifflin(self) -> float:
        """Get the RMR using Mifflin equation."""
        var1 = 10 * Convert.to_kg(self.weight)
        var2 = 6.25 * Convert.to_cm(self.height)
        var3 = 5 * self.age
        additional_kcal = -161 if self.gender == "f" else 5
        return round(self.activity_level * (var1 + var2 - var3 + additional_kcal), 2)

    @property
    def bmi(self) -> float:
        """Calculate BMI."""
        return round(
            Convert.to_kg(self.weight) / (Convert.to_meters(self.height) ** 2),
            2,
        )

    @property
    def ibw(self) -> float:
        """Get Ideal Body Weight."""
        init_wt = 100 if self.gender == "f" else 106
        additional_wt = 5 if self.gender == "f" else 6
        if self.height < MIN_HEIGHT:
            return init_wt - (additional_wt * (60 - self.height))
        return init_wt + (additional_wt * (self.height - 60))

    @property
    def aibw(self) -> float:
        """Get the Adjusted Ideal Body Weight."""
        return ((self.weight - self.ibw) * 0.25) + self.ibw

    @property
    def bmi_adjusted_for_amputation(self) -> float:
        """Get BMI Adjusted for Amputation.

        :param amputation: % of amputation based on limb size
        :return: BMI
        """
        if self.amputation is None:
            msg = "No amputation provided, unable to adjust BMI"
            raise ValueError(msg)
        adj_wt = int(self.weight / (1.0 - (self.amputation * 0.01)))
        return round(Convert.to_kg(adj_wt) / Convert.to_meters(self.height) ** 2, 2)

    @property
    def ibw_adjusted_for_amputation(self) -> float:
        """Get Ideal Body Weight Adjusted for Amputation.

        :param amputation: % of amputation based on limb size
        :return: IBW
        """
        if self.amputation is None:
            msg = "No amputation provided, unable to adjust IBW"
            raise ValueError(msg)
        adjusted = self.ibw * (self.amputation * 0.01)
        return self.ibw - adjusted

    @property
    def aibw_adjusted_for_amputation(self) -> float:
        """Get Adjusted for Obesity IBW and further Adjust for Amputation.

        :param amputation: % of amputation based on limb size
        :return: AIBW
        """
        if self.amputation is None:
            msg = "No amputation provided, unable to adjust Obese IBW"
            raise ValueError(msg)
        adjusted = self.aibw * (self.amputation * 0.01)
        return self.aibw - adjusted

    def _determine_bmi_category(self) -> BMICategory:
        """Determine BMI category."""
        if self.amputation is not None:
            logger.info(
                "Amputation provided, using BMI adjusted for amputation: %s",
                self.bmi_adjusted_for_amputation,
            )
            bmi = self.bmi_adjusted_for_amputation
        else:
            bmi = self.bmi
        ranges = (
            GERIATRIC_BMI_RANGES if self.age >= GERIATRIC_AGE else STANDARD_BMI_RANGES
        )
        return get_bmi_category(bmi, ranges)

    def _determine_weight_basis(self, bmi_category: BMICategory) -> WeightBasis:
        """Determine weight basis based on BMI.

        :raises ValueError: bmi not accounted for
        :return: weight basis name to use for calculations
        """
        match bmi_category:
            case BMICategory.UNDERWEIGHT:
                return WeightBasis.CBW
            case BMICategory.NORMAL:
                return WeightBasis.CBW
            case BMICategory.OVERWEIGHT:
                return WeightBasis.IBW
            case BMICategory.OBESE:
                return WeightBasis.AIBW
            case BMICategory.MORBIDLY_OBESE:
                return WeightBasis.AIBW
        msg = f"Unknown bmi class: {bmi_category}"
        raise ValueError(msg)

    def get_weight(self, basis: WeightBasis) -> float:
        """Get weight to use for calculations based on basis.

        :param basis: Weight basis name
        :return: weight to use for calcs
        """
        match basis:
            case WeightBasis.CBW:
                return self.weight
            case WeightBasis.IBW:
                return self.ibw
            case WeightBasis.AIBW:
                return self.aibw

    @staticmethod
    def get_range(kg: float, scale: tuple[float, float]) -> tuple[int, int]:
        """Calculate range between high and low points for given kg.

        :param kg: base weight you are using
        :param scale: tuple containing low and high range
        :return: min and max values
        """
        low_range = int(kg * scale[0])
        high_range = int(kg * scale[1])
        return (low_range, high_range)
