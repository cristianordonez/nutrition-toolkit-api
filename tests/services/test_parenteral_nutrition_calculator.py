"""Tests for deterministic parenteral-nutrition calculations."""

# ruff: noqa: PLR2004

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ntk.models.sql.clinical import LipidDeliveryType
from ntk.services.calculators.parenteral_nutrition_calculator import (
    ParenteralNutritionCalculationInput,
    ParenteralNutritionCalculator,
)


def test_complete_cyclic_pn_with_piggyback_lipids() -> None:
    result = ParenteralNutritionCalculator.calculate(
        ParenteralNutritionCalculationInput(
            total_volume_ml=1800,
            hours_per_day=12,
            dextrose_g_per_l=200,
            amino_acid_g_per_l=50,
            lipid_delivery=LipidDeliveryType.PIGGYBACK,
            lipid_concentration_percent=20,
            lipid_total_volume_ml=250,
            lipid_run_time_hours=10,
            weight_kg=60,
        ),
    )

    assert result.rate_ml_hr == 150
    assert result.dextrose_g_day == 360
    assert result.amino_acid_g_day == 90
    assert result.calculated_protein_g_day == 90
    assert result.dextrose_kcal_day == 1224
    assert result.amino_acid_kcal_day == 360
    assert result.lipid_g_day == 50
    assert result.lipid_kcal_day == 500
    assert result.total_kcal_day == 2084
    assert result.total_fluid_ml_day == 2050
    assert result.lipid_rate_ml_hr == 25
    assert result.gir_mg_kg_min == 8.33
    assert result.missing_inputs == ()


def test_included_lipid_volume_is_not_added_to_total_fluid() -> None:
    result = ParenteralNutritionCalculator.calculate(
        ParenteralNutritionCalculationInput(
            rate_ml_hr=75,
            hours_per_day=16,
            dextrose_g_per_l=150,
            amino_acid_g_per_l=40,
            lipid_delivery=LipidDeliveryType.INCLUDED,
            lipid_concentration_percent=20,
            lipid_total_volume_ml=200,
        ),
    )

    assert result.total_volume_ml == 1200
    assert result.total_fluid_ml_day == 1200


def test_unknown_lipid_delivery_does_not_produce_partial_totals() -> None:
    result = ParenteralNutritionCalculator.calculate(
        ParenteralNutritionCalculationInput(
            total_volume_ml=1000,
            hours_per_day=10,
            dextrose_g_per_l=200,
            amino_acid_g_per_l=50,
        ),
    )

    assert result.dextrose_g_day == 200
    assert result.calculated_protein_g_day == 50
    assert result.total_kcal_day is None
    assert result.total_fluid_ml_day is None
    assert "lipid_delivery" in result.missing_inputs
    assert "weight_kg_for_gir" in result.missing_inputs


def test_documented_values_remain_separate_and_discrepancies_warn() -> None:
    result = ParenteralNutritionCalculator.calculate(
        ParenteralNutritionCalculationInput(
            total_volume_ml=1000,
            hours_per_day=10,
            dextrose_g_per_l=200,
            amino_acid_g_per_l=50,
            lipid_delivery=LipidDeliveryType.NONE,
            documented_protein_g=75,
            documented_calories_kcal=1000,
        ),
    )

    assert result.calculated_protein_g_day == 50
    assert result.total_kcal_day == 880
    assert result.documented_protein_g == 75
    assert result.documented_calories_kcal == 1000
    assert result.warnings == (
        "Documented protein differs from the deterministic calculation",
        "Documented calories differs from the deterministic calculation",
    )


def test_conflicting_schedule_is_rejected() -> None:
    data = ParenteralNutritionCalculationInput(
        total_volume_ml=1800,
        rate_ml_hr=100,
        hours_per_day=12,
    )

    with pytest.raises(ValueError, match="volume, rate, and duration conflict"):
        ParenteralNutritionCalculator.calculate(data)


def test_invalid_values_are_rejected_by_input_schema() -> None:
    with pytest.raises(ValidationError):
        ParenteralNutritionCalculationInput(total_volume_ml=-1)
