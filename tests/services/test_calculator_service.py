from __future__ import annotations

import typing

import pytest

from ntk.services.calculators import (
    BMICategory,
    EnergyNeedsInput,
    Gender,
    NutritionCalculator,
    RangeResult,
    WeightBasis,
)

_TEST_WEIGHT = 220.0
_TEST_IBW = 142.0
_TEST_AIBW = 161.5


@pytest.mark.parametrize(
    ("height", "weight", "gender", "age", "activity", "expected"),
    [
        (70, 180.0, "m", 30, 1.2, 2141.34),
        (65, 150.0, "f", 25, 1.5, 2141.51),
    ],
)
def test_mifflin(  # noqa: PLR0913
    *,
    height: int,
    weight: float,
    gender: typing.Literal["m", "f"],
    age: int,
    activity: float,
    expected: float,
) -> None:
    assert (
        NutritionCalculator.calculate_mifflin(
            weight,
            height,
            Gender(gender),
            age,
            activity,
        )
        == expected
    )


@pytest.mark.parametrize(
    ("height", "weight", "expected"),
    [
        (70, 180.0, 25.82),
        (64, 140.0, 23.95),
    ],
)
def test_bmi(height: int, weight: float, expected: float) -> None:
    assert NutritionCalculator.calculate_bmi(weight, height) == expected


@pytest.mark.parametrize(
    ("height", "gender", "expected"),
    [
        (66, "m", 142.0),
        (58, "f", 90.0),
    ],
)
def test_ibw(height: int, gender: typing.Literal["m", "f"], expected: float) -> None:
    assert NutritionCalculator.calculate_ibw(Gender(gender), height) == expected


def test_aibw() -> None:
    assert NutritionCalculator.calculate_ibw(Gender.MALE, 66) == _TEST_IBW
    assert (
        NutritionCalculator.calculate_aibw(_TEST_WEIGHT, 66, Gender.MALE) == _TEST_AIBW
    )


@pytest.mark.parametrize(
    ("height", "weight", "amputation", "expected"),
    [
        (66, 180.0, 15.0, 33.98),
        (64, 150.0, 10.0, 28.4),
    ],
)
def test_bmi_adjusted_for_amputation(
    height: int,
    weight: float,
    amputation: float,
    expected: float,
) -> None:
    assert (
        NutritionCalculator.calculate_bmi_adjusted_for_amputation(
            weight,
            height,
            amputation,
        )
        == expected
    )


@pytest.mark.parametrize(
    ("height", "gender", "amputation", "expected"),
    [
        (66, "m", 12.5, 124.25),
        (64, "f", 10.0, 108.0),
    ],
)
def test_ibw_adjusted_for_amputation(
    height: int,
    gender: typing.Literal["m", "f"],
    amputation: float,
    expected: float,
) -> None:
    assert (
        NutritionCalculator.calculate_ibw_adjusted_for_amputation(
            Gender(gender),
            height,
            amputation,
        )
        == expected
    )


@pytest.mark.parametrize(
    ("height", "weight", "amputation", "expected"),
    [
        (66, 220.0, 15.0, 137.275),
        (64, 160.0, 10.0, 123.75),
    ],
)
def test_aibw_adjusted_for_amputation(
    height: int,
    weight: float,
    amputation: float,
    expected: float,
) -> None:
    assert (
        NutritionCalculator.calculate_aibw_adjusted_for_amputation(
            weight,
            height,
            Gender.MALE,
            amputation,
        )
        == expected
    )


@pytest.mark.parametrize(
    ("height", "weight", "age", "expected_category"),
    [
        (68, 115.0, 30, BMICategory.UNDERWEIGHT),
        (68, 150.0, 30, BMICategory.NORMAL),
        (68, 190.0, 30, BMICategory.OVERWEIGHT),
        (68, 230.0, 30, BMICategory.OBESE),
        (68, 300.0, 30, BMICategory.MORBIDLY_OBESE),
    ],
)
def test_determine_bmi_category(
    height: int,
    weight: float,
    age: int,
    expected_category: BMICategory,
) -> None:
    bmi = NutritionCalculator.calculate_bmi(weight, height)
    assert NutritionCalculator.determine_bmi_category(bmi, age) is expected_category


def test_determine_bmi_category_uses_geriatric_recommendation() -> None:
    bmi = NutritionCalculator.calculate_bmi(165.0, 66)
    assert NutritionCalculator.determine_bmi_category(bmi, 75) is BMICategory.NORMAL


@pytest.mark.parametrize(
    ("height", "weight", "expected_basis"),
    [
        (68, 115.0, WeightBasis.CBW),
        (68, 150.0, WeightBasis.CBW),
        (68, 190.0, WeightBasis.IBW),
        (68, 230.0, WeightBasis.AIBW),
        (68, 300.0, WeightBasis.AIBW),
    ],
)
def test_determine_weight_basis(
    height: int,
    weight: float,
    expected_basis: WeightBasis,
) -> None:
    bmi = NutritionCalculator.calculate_bmi(weight, height)
    bmi_category = NutritionCalculator.determine_bmi_category(bmi, 30)
    assert NutritionCalculator.determine_weight_basis(bmi_category) is expected_basis


def test_get_weight_for_basis() -> None:
    weights = {
        "current_weight": _TEST_WEIGHT,
        "ideal_weight": _TEST_IBW,
        "adjusted_weight": _TEST_AIBW,
    }
    assert NutritionCalculator.get_weight(WeightBasis.CBW, **weights) == _TEST_WEIGHT
    assert NutritionCalculator.get_weight(WeightBasis.IBW, **weights) == _TEST_IBW
    assert NutritionCalculator.get_weight(WeightBasis.AIBW, **weights) == _TEST_AIBW


def test_get_range() -> None:
    assert NutritionCalculator.calculate_range(100.0, (0.8, 1.2)) == RangeResult(
        low=80,
        high=120,
    )


def test_calculate_returns_complete_structured_result() -> None:
    result = NutritionCalculator.calculate(
        EnergyNeedsInput(
            height_in=66,
            weight_lb=_TEST_WEIGHT,
            gender=Gender.MALE,
            age=70,
            dialysis=True,
        ),
    )

    assert result.bmi_category == BMICategory.OBESE.name
    assert result.weight_basis == WeightBasis.AIBW.value
    assert result.calculation_weight_lb == _TEST_AIBW
    assert result.protein_factor == RangeResult(low=1.2, high=1.5)
    assert result.calories_kcal_day.low > 0
    assert result.mifflin_kcal_day > 0


def test_calculate_honors_manual_factors() -> None:
    result = NutritionCalculator.calculate(
        EnergyNeedsInput(
            height_in=68,
            weight_lb=150,
            gender=Gender.FEMALE,
            age=40,
            calorie_factor=(22, 27),
            protein_factor=(1.1, 1.3),
        ),
    )

    assert result.calorie_factor == RangeResult(low=22, high=27)
    assert result.protein_factor == RangeResult(low=1.1, high=1.3)
