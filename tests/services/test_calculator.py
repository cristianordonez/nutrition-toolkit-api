from __future__ import annotations

import typing

import pytest

from ntk.services.calculator import BMICategory, Calculator, WeightBasis

# ruff: noqa: S101
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
    height: int,
    weight: float,
    gender: typing.Literal["m", "f"],
    age: int,
    activity: float,
    expected: float,
) -> None:
    calculator = Calculator(height, weight, gender, age, activity)
    assert calculator.mifflin == expected


@pytest.mark.parametrize(
    ("height", "weight", "expected"),
    [
        (70, 180.0, 25.82),
        (64, 140.0, 23.95),
    ],
)
def test_bmi(height: int, weight: float, expected: float) -> None:
    calculator = Calculator(height, weight, "m", 30)
    assert calculator.bmi == expected


@pytest.mark.parametrize(
    ("height", "gender", "expected"),
    [
        (66, "m", 142.0),
        (58, "f", 90.0),
    ],
)
def test_ibw(height: int, gender: typing.Literal["m", "f"], expected: float) -> None:
    calculator = Calculator(height, 150.0, gender, 30)
    assert calculator.ibw == expected


def test_aibw() -> None:
    calculator = Calculator(66, _TEST_WEIGHT, "m", 30)
    assert calculator.ibw == _TEST_IBW
    assert calculator.aibw == _TEST_AIBW


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
    calculator = Calculator(height, weight, "f", 40, amputation=amputation)
    assert calculator.bmi_adjusted_for_amputation == expected


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
    calculator = Calculator(height, 150.0, gender, 35, amputation=amputation)
    assert calculator.ibw_adjusted_for_amputation == expected


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
    calculator = Calculator(height, weight, "m", 50, amputation=amputation)
    assert calculator.aibw_adjusted_for_amputation == expected


@pytest.mark.parametrize(
    ("property_name", "error_message"),
    [
        ("bmi_adjusted_for_amputation", "No amputation provided, unable to adjust BMI"),
        ("ibw_adjusted_for_amputation", "No amputation provided, unable to adjust IBW"),
        (
            "aibw_adjusted_for_amputation",
            "No amputation provided, unable to adjust Obese IBW",
        ),
    ],
)
def test_amputation_properties_raise_when_missing(
    property_name: str,
    error_message: str,
) -> None:
    calculator = Calculator(66, 180.0, "f", 40)
    with pytest.raises(ValueError, match=error_message):
        getattr(calculator, property_name)


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
    calculator = Calculator(height, weight, "m", age)
    assert calculator.determine_bmi_category() is expected_category


def test_determine_bmi_category_uses_geriatric_recommendation() -> None:
    calculator = Calculator(66, 165.0, "m", 75)
    assert calculator.determine_bmi_category() is BMICategory.NORMAL


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
    calculator = Calculator(height, weight, "m", 30)
    assert calculator.determine_weight_basis() is expected_basis


def test_get_weight_for_basis() -> None:
    calculator = Calculator(66, _TEST_WEIGHT, "m", 30)
    assert calculator.get_weight(WeightBasis.CBW) == _TEST_WEIGHT
    assert calculator.get_weight(WeightBasis.IBW) == _TEST_IBW
    assert calculator.get_weight(WeightBasis.AIBW) == _TEST_AIBW


def test_get_range() -> None:
    assert Calculator.get_range(100.0, (0.8, 1.2)) == (80, 120)
