from __future__ import annotations

# ruff: noqa: S101
from ntk.controllers.calculate.energy import EnergyController, EnergyOptions
from ntk.domain.calculator import Calculator

_TEST_WEIGHT = 180.0
_TEST_HEIGHT = 70
_TEST_AGE = 30


def test_energy_controller_run_returns_expected_output() -> None:
    options = EnergyOptions(weight=_TEST_WEIGHT, height=_TEST_HEIGHT, age=_TEST_AGE)
    output = EnergyController().run(options)
    assert output.controller == "energy"
    assert output.exit_code == 0

    result = output.result
    calc = Calculator(
        height=_TEST_HEIGHT,
        weight=_TEST_WEIGHT,
        gender="m",
        age=_TEST_AGE,
        activity_level=options.activity_level,
    )

    assert result["BMI"] == calc.bmi
    assert result["CBW"] == _TEST_WEIGHT
    assert result["Mifflin"] == calc.mifflin
    assert result["IBW"] == calc.ibw
    assert result["kcal"].endswith(" kcal (25-30 kcal/kg)")
    assert result["protein"].endswith(" g (1.0-1.2 g/kg)")
    assert result["fluid"].endswith(" mL (25-30 mL/kg)")
    assert result["Calculations done using"].startswith("Ideal Body Weight")


def test_energy_controller_uses_dialysis_protein_needs() -> None:
    options = EnergyOptions(
        weight=100.0,
        height=65,
        age=60,
        dialysis=True,
    )
    output = EnergyController().run(options)
    assert output.result["protein"].endswith(" g (1.2-1.5 g/kg)")


def test_energy_controller_accepts_manual_ranges() -> None:
    options = EnergyOptions(
        weight=150.0,
        height=68,
        age=40,
        energy_needs=(20, 25),
        protein_needs=(1.1, 1.3),
    )
    output = EnergyController().run(options)

    assert output.result["kcal"].endswith(" kcal (20-25 kcal/kg)")
    assert output.result["protein"].endswith(" g (1.1-1.3 g/kg)")


def test_energy_controller_includes_amputation_adjustments() -> None:
    options = EnergyOptions(
        weight=_TEST_WEIGHT,
        height=_TEST_HEIGHT,
        age=_TEST_AGE,
        amputation=10.0,
    )
    output = EnergyController().run(options)

    assert "BMI Adjusted for Amputation" in output.result
    assert "IBW Adjusted for Amputation" in output.result
