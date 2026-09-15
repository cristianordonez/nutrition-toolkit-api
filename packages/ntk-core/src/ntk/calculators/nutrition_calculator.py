from __future__ import annotations

import logging
import typing
from enum import Enum, StrEnum

from pydantic import BaseModel, Field

from ntk.utils.convert import Convert

logger = logging.getLogger(__name__)

_MIN_HEIGHT = 60.0
_GERIATRIC_AGE = 65
_RANGE_LENGTH = 2
_FloatFactorRange = typing.Annotated[
    tuple[float, ...],
    Field(min_length=_RANGE_LENGTH, max_length=_RANGE_LENGTH),
]
_IntegerFactorRange = typing.Annotated[
    tuple[int, ...],
    Field(min_length=_RANGE_LENGTH, max_length=_RANGE_LENGTH),
]


class BMICategory(Enum):
    """BMI classifications returned by adult and geriatric categorization."""

    UNDERWEIGHT = "Underweight"
    NORMAL = "Normal"
    OVERWEIGHT = "Overweight"
    OBESE = "Obese"
    MORBIDLY_OBESE = "Morbidly Obese"


_STANDARD_BMI_RANGES = {
    BMICategory.UNDERWEIGHT: (0.0, 18.5),
    BMICategory.NORMAL: (18.5, 25.0),
    BMICategory.OVERWEIGHT: (25.0, 30.0),
    BMICategory.OBESE: (30.0, 40.0),
    BMICategory.MORBIDLY_OBESE: (40.0, float("inf")),
}

_GERIATRIC_BMI_RANGES = {
    BMICategory.UNDERWEIGHT: (0.0, 22.0),
    BMICategory.NORMAL: (22.0, 28.0),
    BMICategory.OVERWEIGHT: (28.0, 30.0),
    BMICategory.OBESE: (30.0, 40.0),
    BMICategory.MORBIDLY_OBESE: (40.0, float("inf")),
}


def _get_bmi_category(
    bmi: float,
    ranges: dict[BMICategory, tuple[float, float]],
) -> BMICategory:
    """Classify a calculated BMI using the supplied category boundaries.

    Args:
        bmi: Previously calculated BMI in kg/m^2.
        ranges: Lower-inclusive and upper-exclusive bounds for each category.

    Returns:
        The category containing the BMI.

    """
    for range_category, (lower, upper) in ranges.items():
        if lower <= bmi < upper:
            return range_category
    msg = f"Invalid BMI: {bmi}"
    raise ValueError(msg)


class WeightBasis(Enum):
    """Supported body-weight bases for calorie, protein, and fluid estimates."""

    CBW = "Current Body Weight"
    IBW = "Ideal Body Weight"
    AIBW = "Ideal Body Weight Adjusted for Obesity"


class RangeResult(BaseModel):
    """Named low and high values for a calculated factor range."""

    low: float
    high: float


class Gender(StrEnum):
    """Gender categories supported by the Hamwi and Mifflin equations."""

    MALE = "m"
    FEMALE = "f"


class Goal(StrEnum):
    """Documented body-weight direction used to select calorie factors."""

    LOSE = "lose"
    MAINTAIN = "maintain"
    GAIN = "gain"


class EnergyNeedsInput(BaseModel):
    """Documented person inputs for a complete nutrition-needs calculation."""

    height_in: float = Field(description="Documented height in inches", gt=0)
    weight_lb: float = Field(
        description="Documented current body weight in pounds",
        gt=0,
    )
    gender: Gender = Field(description="Documented equation category: m or f")
    age: int = Field(description="Documented age in completed years", gt=0, le=120)
    activity_level: float = Field(
        default=1.2,
        description="Documented or clinically selected activity multiplier",
        gt=0,
    )
    amputation_percent: float | None = Field(
        default=None,
        description=(
            "Documented percent of total body weight represented by limb loss; "
            "omit when no amputation adjustment applies"
        ),
        ge=0,
        lt=100,
    )
    goal: Goal = Field(
        default=Goal.MAINTAIN,
        description="Documented weight goal used to select default calorie factors",
    )
    dialysis: bool = Field(
        default=False,
        description="Whether the person is documented as receiving dialysis",
    )
    protein_factor: _FloatFactorRange | None = Field(
        default=None,
        description=(
            "Optional prescribed low/high protein factors in g/kg; omit to use "
            "dialysis-based defaults"
        ),
    )
    calorie_factor: _IntegerFactorRange | None = Field(
        default=None,
        description=(
            "Optional prescribed low/high calorie factors in kcal/kg; omit to use "
            "goal-based defaults"
        ),
    )


class EnergyNeedsResult(BaseModel):
    """Structured outputs from a complete nutrition-needs calculation."""

    bmi: float
    bmi_category: str
    current_weight_lb: float
    ideal_weight_lb: float
    adjusted_weight_lb: float
    calculation_weight_lb: float
    calculation_weight_kg: float
    weight_basis: str
    calorie_factor: RangeResult
    protein_factor: RangeResult
    fluid_factor: RangeResult
    calories_kcal_day: RangeResult
    protein_g_day: RangeResult
    fluids_ml_day: RangeResult
    mifflin_kcal_day: float


class NutritionCalculator:
    """Calculate nutrition metrics only from documented person measurements."""

    @staticmethod
    def calculate(data: EnergyNeedsInput) -> EnergyNeedsResult:
        """Calculate a complete daily nutrition-needs profile.

        Use this as the preferred tool when documented height, current weight,
        gender, and age are available and the assessment needs BMI, weight basis,
        calorie, protein, fluid, and Mifflin estimates together. Supply a documented
        amputation percentage, dialysis status, weight goal, or prescribed factors
        when available; never infer missing inputs. Use a narrower calculator tool
        when only one metric is needed.

        Args:
            data: Documented person measurements and clinical calculation options.

        Returns:
            Structured BMI, calculation-weight, factor, and daily-needs estimates.

        """
        bmi = (
            NutritionCalculator.calculate_bmi_adjusted_for_amputation(
                data.weight_lb,
                data.height_in,
                data.amputation_percent,
            )
            if data.amputation_percent is not None
            else NutritionCalculator.calculate_bmi(data.weight_lb, data.height_in)
        )
        bmi_category = NutritionCalculator.determine_bmi_category(bmi, data.age)
        weight_basis = NutritionCalculator.determine_weight_basis(bmi_category)
        ideal_weight = NutritionCalculator.calculate_ibw(data.gender, data.height_in)
        adjusted_weight = NutritionCalculator.calculate_aibw(
            data.weight_lb,
            data.height_in,
            data.gender,
        )
        calculation_weight = NutritionCalculator.get_weight(
            weight_basis,
            current_weight=data.weight_lb,
            ideal_weight=ideal_weight,
            adjusted_weight=adjusted_weight,
        )
        calculation_weight_kg = Convert.to_kg(calculation_weight)
        calorie_factor = NutritionCalculator.get_calorie_factor(
            data.goal,
            data.calorie_factor,
        )
        protein_factor = NutritionCalculator.get_protein_factor(
            dialysis=data.dialysis,
            protein_factor=data.protein_factor,
        )
        fluid_factor = calorie_factor
        return EnergyNeedsResult(
            bmi=bmi,
            bmi_category=bmi_category.name,
            current_weight_lb=data.weight_lb,
            ideal_weight_lb=ideal_weight,
            adjusted_weight_lb=adjusted_weight,
            calculation_weight_lb=calculation_weight,
            calculation_weight_kg=calculation_weight_kg,
            weight_basis=weight_basis.value,
            calorie_factor=NutritionCalculator.to_range_result(calorie_factor),
            protein_factor=NutritionCalculator.to_range_result(protein_factor),
            fluid_factor=NutritionCalculator.to_range_result(fluid_factor),
            calories_kcal_day=NutritionCalculator.calculate_range(
                calculation_weight_kg,
                calorie_factor,
            ),
            protein_g_day=NutritionCalculator.calculate_range(
                calculation_weight_kg,
                protein_factor,
            ),
            fluids_ml_day=NutritionCalculator.calculate_range(
                calculation_weight_kg,
                fluid_factor,
            ),
            mifflin_kcal_day=NutritionCalculator.calculate_mifflin(
                data.weight_lb,
                data.height_in,
                data.gender,
                data.age,
                data.activity_level,
            ),
        )

    @staticmethod
    def get_calorie_factor(
        goal: Goal,
        calorie_factor: _IntegerFactorRange | None = None,
    ) -> tuple[int, int]:
        """Select a kcal/kg factor range for a documented weight goal.

        Args:
            goal: Whether the documented goal is weight loss, maintenance, or gain.
            calorie_factor: Optional prescribed low/high kcal/kg factors, which take
                precedence over the goal-based defaults.

        Returns:
            Low and high kcal/kg factors.

        """
        if calorie_factor is not None:
            return calorie_factor[0], calorie_factor[1]
        if goal is Goal.LOSE:
            return (20, 25)
        if goal is Goal.GAIN:
            return (30, 35)
        return (25, 30)

    @staticmethod
    def get_protein_factor(
        *,
        dialysis: bool,
        protein_factor: _FloatFactorRange | None = None,
    ) -> tuple[float, float]:
        """Select a g/kg protein factor range using documented dialysis status.

        Args:
            dialysis: Whether the person is documented as receiving dialysis.
            protein_factor: Optional prescribed low/high g/kg factors, which take
                precedence over the dialysis-based defaults.

        Returns:
            Low and high protein factors in g/kg.

        """
        if protein_factor is not None:
            logger.debug("Using manually set protein needs: %s", protein_factor)
            return protein_factor[0], protein_factor[1]
        if dialysis:
            logger.debug("Dialysis is True, using protein needs of 1.2-1.5 g/kg")
            return (1.2, 1.5)
        return (1.0, 1.2)

    @staticmethod
    def calculate_mifflin(
        weight_lb: float,
        height_in: float,
        gender: Gender,
        age: int,
        activity_level: float = 1.2,
    ) -> float:
        """Estimate daily energy with the activity-adjusted Mifflin-St Jeor equation.

        Use when the assessment specifically needs a Mifflin estimate and documented
        current weight, height, gender, age, and an appropriate activity factor are
        available. Use ``calculate`` instead when a complete nutrition-needs profile
        is needed. Inputs must be pounds, inches, years, and a unitless activity
        multiplier; do not use this tool to select an activity factor.

        Args:
            weight_lb: Documented current body weight in pounds.
            height_in: Documented height in inches.
            gender: Documented equation category: ``m`` or ``f``.
            age: Documented age in completed years.
            activity_level: Documented or clinically selected activity multiplier.

        Returns:
            Activity-adjusted energy estimate in kcal/day.

        """
        weight_component = 10 * Convert.to_kg(weight_lb)
        height_component = 6.25 * Convert.to_cm(height_in)
        age_component = 5 * age
        additional_kcal = -161 if gender is Gender.FEMALE else 5
        return round(
            activity_level
            * (weight_component + height_component - age_component + additional_kcal),
            2,
        )

    @staticmethod
    def calculate_bmi(weight_lb: float, height_in: float) -> float:
        """Calculate unadjusted BMI from a documented weight and height.

        Use for a person without a documented amputation, or when an explicitly
        unadjusted BMI is required. Use ``calculate_bmi_adjusted_for_amputation``
        when a documented amputation percentage must be included.

        Args:
            weight_lb: Documented current body weight in pounds.
            height_in: Documented height in inches.

        Returns:
            BMI in kg/m^2, rounded to two decimal places.

        """
        return round(
            Convert.to_kg(weight_lb) / (Convert.to_meters(height_in) ** 2),
            2,
        )

    @staticmethod
    def calculate_ibw(gender: Gender, height_in: float) -> float:
        """Calculate unadjusted ideal body weight using the Hamwi equation.

        Use when documented height and gender are available and an IBW in pounds is
        needed. This result is not adjusted for obesity or limb loss; use the
        corresponding adjusted tool when either adjustment is required.

        Args:
            gender: Documented equation category: ``m`` or ``f``.
            height_in: Documented height in inches.

        Returns:
            Ideal body weight in pounds.

        """
        initial_weight = 100 if gender is Gender.FEMALE else 106
        additional_weight = 5 if gender is Gender.FEMALE else 6
        if height_in < _MIN_HEIGHT:
            return initial_weight - (additional_weight * (_MIN_HEIGHT - height_in))
        return initial_weight + (additional_weight * (height_in - _MIN_HEIGHT))

    @staticmethod
    def calculate_aibw(weight_lb: float, height_in: float, gender: Gender) -> float:
        """Calculate ideal body weight adjusted for obesity.

        Use when obesity makes adjusted ideal body weight an appropriate basis for
        nutrition-needs calculations. Do not use for a non-obese person merely
        because current weight differs from IBW. This result is not adjusted for an
        amputation.

        Args:
            weight_lb: Documented current body weight in pounds.
            height_in: Documented height in inches.
            gender: Documented equation category: ``m`` or ``f``.

        Returns:
            Obesity-adjusted ideal body weight in pounds.

        """
        ideal_weight = NutritionCalculator.calculate_ibw(gender, height_in)
        return ((weight_lb - ideal_weight) * 0.25) + ideal_weight

    @staticmethod
    def calculate_bmi_adjusted_for_amputation(
        weight_lb: float,
        height_in: float,
        amputation_percent: float,
    ) -> float:
        """Calculate BMI adjusted for a documented amputation percentage.

        Use only when the person has a documented total body-weight percentage
        attributable to limb loss. Do not guess the percentage from an imprecise
        amputation description; use ``calculate_bmi`` when no adjustment applies.

        Args:
            weight_lb: Documented post-amputation current weight in pounds.
            height_in: Documented height in inches.
            amputation_percent: Documented percent of total body weight represented
                by the missing limb or body segment, expressed from 0 to less than
                100 (for example, ``5.9`` means 5.9%).

        Returns:
            Amputation-adjusted BMI in kg/m^2.

        """
        adjusted_weight = int(weight_lb / (1.0 - (amputation_percent * 0.01)))
        return NutritionCalculator.calculate_bmi(adjusted_weight, height_in)

    @staticmethod
    def calculate_ibw_adjusted_for_amputation(
        gender: Gender,
        height_in: float,
        amputation_percent: float,
    ) -> float:
        """Calculate ideal body weight adjusted for documented limb loss.

        Use when an IBW in pounds is required for a person with a documented
        amputation percentage. This adjusts Hamwi IBW for limb loss but does not
        apply the obesity adjustment.

        Args:
            gender: Documented equation category: ``m`` or ``f``.
            height_in: Documented height in inches.
            amputation_percent: Documented percent of total body weight represented
                by the missing limb or body segment, expressed from 0 to less than
                100.

        Returns:
            Amputation-adjusted ideal body weight in pounds.

        """
        ideal_weight = NutritionCalculator.calculate_ibw(gender, height_in)
        return ideal_weight - (ideal_weight * (amputation_percent * 0.01))

    @staticmethod
    def calculate_aibw_adjusted_for_amputation(
        weight_lb: float,
        height_in: float,
        gender: Gender,
        amputation_percent: float,
    ) -> float:
        """Calculate obesity-adjusted ideal body weight adjusted for limb loss.

        Use only when both obesity adjustment and a documented amputation percentage
        apply. Prefer ``calculate_aibw`` when there is no amputation and
        ``calculate_ibw_adjusted_for_amputation`` when obesity adjustment is not
        appropriate.

        Args:
            weight_lb: Documented current body weight in pounds.
            height_in: Documented height in inches.
            gender: Documented equation category: ``m`` or ``f``.
            amputation_percent: Documented percent of total body weight represented
                by the missing limb or body segment, expressed from 0 to less than
                100.

        Returns:
            Obesity- and amputation-adjusted ideal body weight in pounds.

        """
        adjusted_ideal_weight = NutritionCalculator.calculate_aibw(
            weight_lb,
            height_in,
            gender,
        )
        return adjusted_ideal_weight - (
            adjusted_ideal_weight * (amputation_percent * 0.01)
        )

    @staticmethod
    def determine_bmi_category(bmi: float, age: int) -> BMICategory:
        """Classify BMI using standard adult or age-65-and-older boundaries.

        Args:
            bmi: Previously calculated BMI in kg/m^2.
            age: Documented age in completed years.

        Returns:
            The applicable BMI category.

        """
        ranges = (
            _GERIATRIC_BMI_RANGES if age >= _GERIATRIC_AGE else _STANDARD_BMI_RANGES
        )
        return _get_bmi_category(bmi, ranges)

    @staticmethod
    def determine_weight_basis(bmi_category: BMICategory) -> WeightBasis:
        """Choose the calculation-weight basis associated with a BMI category.

        Args:
            bmi_category: BMI category already determined for the person.

        Returns:
            Current weight for underweight/normal BMI, IBW for overweight BMI, or
            adjusted IBW for obese/morbidly obese BMI.

        Raises:
            ValueError: If the BMI category is unsupported.

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

    @staticmethod
    def get_weight(
        basis: WeightBasis,
        *,
        current_weight: float,
        ideal_weight: float,
        adjusted_weight: float,
    ) -> float:
        """Return the supplied weight value selected by a weight-basis decision.

        Args:
            basis: Previously selected current, ideal, or adjusted-ideal basis.
            current_weight: Documented current body weight in pounds.
            ideal_weight: Previously calculated ideal body weight in pounds.
            adjusted_weight: Previously calculated adjusted ideal weight in pounds.

        Returns:
            The selected calculation weight in pounds.

        Raises:
            ValueError: If the weight basis is unsupported.

        """
        match basis:
            case WeightBasis.CBW:
                return current_weight
            case WeightBasis.IBW:
                return ideal_weight
            case WeightBasis.AIBW:
                return adjusted_weight
        msg = f"Unknown weight basis: {basis}"
        raise ValueError(msg)

    @staticmethod
    def calculate_range(kg: float, scale: _FloatFactorRange) -> RangeResult:
        """Convert a documented kg-based factor pair into a daily target range.

        Use when a calculation weight in kilograms and an already selected low/high
        factor pair are available. For example, kg x kcal/kg yields kcal/day and kg
        x g/kg yields g/day. This tool does not choose clinically appropriate
        factors; use ``calculate`` when factors and the weight basis must be selected.

        Args:
            kg: Documented or previously calculated weight basis in kilograms.
            scale: Exactly two ordered factors: low then high.

        Returns:
            Integer low and high products in the units implied by the factors.

        Raises:
            ValueError: If the factor pair does not contain exactly two values.

        """
        if len(scale) != _RANGE_LENGTH:
            message = "Scale must contain exactly two values"
            raise ValueError(message)
        low_range = int(kg * scale[0])
        high_range = int(kg * scale[1])
        return RangeResult(low=low_range, high=high_range)

    @staticmethod
    def to_range_result(scale: _FloatFactorRange) -> RangeResult:
        """Represent an internal low/high factor pair as a structured result.

        Args:
            scale: Exactly two ordered numeric factors: low then high.

        Returns:
            The factors represented as named ``low`` and ``high`` values.

        """
        return RangeResult(low=scale[0], high=scale[1])


__all__ = [
    "BMICategory",
    "EnergyNeedsInput",
    "EnergyNeedsResult",
    "Gender",
    "Goal",
    "NutritionCalculator",
    "RangeResult",
    "WeightBasis",
]
