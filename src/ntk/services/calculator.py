from __future__ import annotations

import logging
import typing
from enum import Enum

from ntk.utils.convert import Convert

logger = logging.getLogger(__name__)

MIN_HEIGHT = 60

GERIATRIC_AGE = 75


class BMICategory(Enum):
    """Contains BMI ranges."""

    UNDERWEIGHT = (0.0, 18.5)
    NORMAL = (18.5, 25.0)
    OVERWEIGHT = (25.0, 30.0)
    OBESE = (30.0, 40.0)
    MORBIDLY_OBESE = (40.0, float("inf"))
    # Recommended BMI range for adults >75 years
    GERIATRIC_RECOMMENDED = (23.0, 28.0)

    def __init__(self, lower: float, upper: float) -> None:
        """Init instance.

        :param lower: min bmi range
        :param upper: max bmi range
        """
        self.lower = lower
        self.upper = upper

    def contains(self, bmi: float) -> bool:
        """Check if BMI is within current range.

        :param bmi: BMI float
        :return: True if within range
        """
        return self.lower <= bmi < self.upper

    @classmethod
    def classify(cls, bmi: float) -> BMICategory:
        """Return the standard BMI classification."""
        for category in (
            cls.UNDERWEIGHT,
            cls.NORMAL,
            cls.OVERWEIGHT,
            cls.OBESE,
            cls.MORBIDLY_OBESE,
        ):
            if category.contains(bmi):
                return category
        msg = f"Invalid BMI: {bmi}"
        raise ValueError(msg)

    @classmethod
    def is_geriatric_recommended(cls, bmi: float) -> bool:
        """Return True if BMI is within the recommended range for adults >75."""
        return cls.GERIATRIC_RECOMMENDED.contains(bmi)


class WeightBasis(Enum):
    """Weight to use for calculations."""

    CBW = "Current Body Weight"
    IBW = "Ideal Body Weight"
    AIBW = "Ideal Body Weight Adjusted for Obesity"


class CalculatorService:
    """Handles nutrition calculations."""

    def __init__(  # noqa: PLR0913
        self,
        height: int,
        weight: float,
        gender: typing.Literal["m", "f"],
        age: int,
        activity_level: float = 1.2,
        amputation: float | None = None,
    ) -> None:
        """Initialize calculator class.

        :param height: height in inches
        :param weight: weight in lbs
        :param gender: users gender, m or f
        :param age: age in years
        :param activity_level: how active user is, usually 1 - 1.9
        :param amputation: percentage of limb removed or none
        """
        self.height = height
        self.weight = weight
        self.gender = gender
        self.age = age
        self.activity_level = activity_level
        self.amputation = amputation

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

    def determine_bmi_category(self) -> BMICategory:
        """Determine BMI category."""
        bmi = self.bmi
        bmi_class = BMICategory.classify(bmi)
        if self.age >= GERIATRIC_AGE and BMICategory.is_geriatric_recommended(bmi):
            logger.info(
                "Age is %s and BMI is %s, using Geriatric BMI limit",
                self.age,
                bmi,
            )
            bmi_class = BMICategory.NORMAL
        return bmi_class

    def determine_weight_basis(self) -> WeightBasis:
        """Determine weight basis based on BMI.

        :raises ValueError: bmi not accounted for
        :return: weight basis name to use for calculations
        """
        bmi_category = self.determine_bmi_category()
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
