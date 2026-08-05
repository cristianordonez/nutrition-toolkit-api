from __future__ import annotations

# ruff: noqa: S101
from ntk.controllers.calculate.energy import EnergyController, EnergyOptions
from ntk.services.calculator_service import CalculatorService

_TEST_WEIGHT = 180.0
_TEST_HEIGHT = 70
_TEST_AGE = 30


def test_energy_controller_run_returns_expected_output() -> None:
    options = EnergyOptions(weight=_TEST_WEIGHT, height=_TEST_HEIGHT, age=_TEST_AGE)
    output = EnergyController().run(options)
    assert output.controller == "energy"
    assert output.exit_code == 0

    result = output.result
    calc = CalculatorService(
        height=_TEST_HEIGHT,
        weight=_TEST_WEIGHT,
        gender="m",
        age=_TEST_AGE,
        activity_level=options.activity_level,
    )
    assert result.bmi == calc.bmi
    assert result.cbw == _TEST_WEIGHT
    assert result.mifflin == calc.mifflin
    assert result.ibw == calc.ibw
    assert result.calories == (
        int(result.weight_used_for_calculations_in_kg * 25),
        int(result.weight_used_for_calculations_in_kg * 30),
    )
    assert result.protein == (
        int(result.weight_used_for_calculations_in_kg * 1.0),
        int(result.weight_used_for_calculations_in_kg * 1.2),
    )
    assert result.calculations_done_using == "Ideal Body Weight"


def test_energy_controller_uses_dialysis_protein_needs() -> None:
    options = EnergyOptions(
        weight=100.0,
        height=65,
        age=60,
        dialysis=True,
    )
    output = EnergyController().run(options)
    min_protein = 1.2
    assert output.result.protein_factor[0] == min_protein


def test_energy_controller_accepts_manual_ranges() -> None:
    options = EnergyOptions(
        weight=150.0,
        height=68,
        age=40,
        energy_needs=(22, 27),
        protein_needs=(1.1, 1.3),
    )
    output = EnergyController().run(options)
    assert output.result["kcal"].endswith(" kcal (20-25 kcal/kg)")
    assert output.result["protein"].endswith(" g (1.1-1.3 g/kg)")
    min_kcal = 22
    max_kcal = 27
    min_protein = 1.1
    max_protein = 1.3
    assert output.result.calorie_factor[0] == min_kcal
    assert output.result.calorie_factor[1] == max_kcal
    assert output.result.protein_factor[0] == min_protein
    assert output.result.protein_factor[1] == max_protein


def test_energy_controller_includes_amputation_adjustments() -> None:
    options = EnergyOptions(
        weight=_TEST_WEIGHT,
        height=_TEST_HEIGHT,
        age=_TEST_AGE,
        amputation=10.0,
    )
    output = EnergyController().run(options)
    assert output.result.bmi_adjusted_for_amputation is not None
    assert output.result.ibw_adjusted_for_amputation is not None
