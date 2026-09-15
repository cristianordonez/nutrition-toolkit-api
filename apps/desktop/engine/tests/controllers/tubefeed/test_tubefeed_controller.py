from __future__ import annotations

import pytest

from engine.controllers.tubefeed.calculate import (
    CalculateTubefeedController,
    CalculateTubefeedOptions,
    CalculateTubefeedResponse,
)
from engine.data.enteral_formulas import Formula, LocalFormulaCatalog
from engine.models.sql.clinical import (
    ClinicalStatus,
    FeedingMethod,
    PersonEnteralFeeding,
)
from engine.services.calculators.tubefeed_calculator import TubeFeedCalculator
from ntk.models.food_vocab import PackageType

_READY_TO_HANG_SERVING_ML = 1000
_READY_TO_HANG_CALORIES = 1200
_CARTON_SERVING_ML = 237
_CARTON_CALORIES = 285


def test_tubefeed_run_returns_success_output() -> None:
    controller = CalculateTubefeedController()
    options = CalculateTubefeedOptions(
        energy_needs=(1800, 2000),
        formula="jevity 1.5",
        package_volume_ml=1000,
    )
    output = controller.run(options)
    assert output.controller == "calculate"
    assert output.exit_code == 0
    assert isinstance(output.result, CalculateTubefeedResponse)
    result = output.result.tubefeed_results
    assert result is not None
    assert result.formula_display_name == "JEVITY 1.5"
    assert result.total_volume_ml == 1300  # noqa: PLR2004
    assert result.rate_ml_per_hr == 70  # noqa: PLR2004
    assert result.kcal_per_day == 1950  # noqa: PLR2004
    assert result.protein_per_day_g == 82.9  # noqa: PLR2004
    assert result.fluids_per_day_ml == 988  # noqa: PLR2004
    assert result.free_water_flush is not None
    assert result.free_water_flush.total_volume_ml == 1000  # noqa: PLR2004
    assert result.free_water_flush.rate_ml_per_hr == 60  # noqa: PLR2004
    assert output.result.to_console() == (
        "Rec JEVITY 1.5 @ 70 ml/hr via PEG up at 4pm. "
        "AND every day shift document total volume infused in 24 hrs (1300 ml). "
        "FWF @ 60 ml/hr to provide TV 1000 mls. "
        "TF + FWF are providing res with 1950 kcal, 82.9 g PRO and "
        "1988 mls fluids."
    )


def test_continuous_output_places_goal_rate_before_optional_titration() -> None:
    output = CalculateTubefeedController().run(
        CalculateTubefeedOptions(
            energy_needs=(1800, 2000),
            formula="jevity 1.5",
            package_volume_ml=1000,
            starting_rate_ml_per_hr=20,
            rate_increase_ml_per_hr=10,
        ),
    )

    assert output.exit_code == 0
    assert output.result.to_console().startswith(
        "Rec JEVITY 1.5 @ 70 ml/hr via PEG up at 4pm. "
        "START AT 20 ML/HR. INCREASE BY 10 ML EVERY HOUR UNTIL 70ML/HR.",
    )


def test_continuous_titration_requires_start_and_increase() -> None:
    output = CalculateTubefeedController().run(
        CalculateTubefeedOptions(
            energy_needs=(1800, 2000),
            formula="jevity 1.5",
            package_volume_ml=1000,
            starting_rate_ml_per_hr=20,
        ),
    )

    assert output.exit_code == 1
    assert output.result.tubefeed_results is None


def test_tubefeed_run_calculates_bolus_feeding() -> None:
    output = CalculateTubefeedController().run(
        CalculateTubefeedOptions(
            energy_needs=(1800, 2000),
            formula="jevity 1.5",
            package_volume_ml=237,
            bolus=True,
            n_bolus_feeds=4,
        ),
    )

    assert output.exit_code == 0
    result = output.result.tubefeed_results
    assert result is not None
    assert result.formula.package_type is PackageType.CARTON
    assert result.n_bolus_feeds == 4  # noqa: PLR2004
    assert result.volume_per_bolus_ml == 325  # noqa: PLR2004
    assert result.rate_ml_per_hr is None
    assert result.free_water_flush is not None
    assert result.free_water_flush.n_bolus_flushes == 8  # noqa: PLR2004
    assert result.free_water_flush.pre_post_bolus_flush is True
    assert result.free_water_flush.pre_post_bolus_volume_ml == 125  # noqa: PLR2004
    assert output.result.to_console() == (
        "Enteral feeding JEVITY 1.5 325 ml via PEG 4 times daily. "
        "AND every day shift document total volume infused in 24 hrs (1300 ml). "
        "FWF 125 ml before and after each bolus to provide TV 1000 mls. "
        "TF + FWF are providing res with 1947 kcal, 82.8 g PRO and "
        "1987.3 mls fluids."
    )


def test_tubefeed_output_includes_protein_supplement_totals() -> None:
    output = CalculateTubefeedController().run(
        CalculateTubefeedOptions(
            energy_needs=(1800, 2000),
            formula="jevity 1.5",
            package_volume_ml=1000,
            protein_supplement_protein_g=24.6,
        ),
    )

    assert output.result.to_console().endswith(
        "TF + FWF + Protein supplement are providing res with 1950 kcal, "
        "107.5 g PRO and 1988 mls fluids.",
    )


def test_tubefeed_run_requires_number_of_bolus_feeds() -> None:
    output = CalculateTubefeedController().run(
        CalculateTubefeedOptions(
            energy_needs=(1800, 2000),
            formula="jevity 1.5",
            package_volume_ml=237,
            bolus=True,
        ),
    )

    assert output.exit_code == 1
    assert output.result.tubefeed_results is None


def test_find_formula_returns_requested_ready_to_hang_volume() -> None:
    formula = TubeFeedCalculator(LocalFormulaCatalog()).find_formula(
        "jevity 1.2",
        package_type=PackageType.READY_TO_HANG,
        package_volume_ml=1000,
    )
    assert formula.name == "jevity 1.2 1L ready-to-hang"
    assert formula.package_type is PackageType.READY_TO_HANG
    assert formula.serving_size == _READY_TO_HANG_SERVING_ML
    assert _nutrient_amount(formula, 1008) == _READY_TO_HANG_CALORIES


def test_find_formula_returns_requested_carton() -> None:
    formula = TubeFeedCalculator(LocalFormulaCatalog()).find_formula(
        "jevity 1.2",
        package_type=PackageType.CARTON,
        package_volume_ml=237,
    )
    assert formula.name == "jevity 1.2 237 mL carton"
    assert formula.serving_size == _CARTON_SERVING_ML
    assert formula.serving_unit == "mL"
    assert formula.package_type is PackageType.CARTON
    assert _nutrient_amount(formula, 1008) == _CARTON_CALORIES


def test_find_formula_raises_for_unknown_formula() -> None:
    with pytest.raises(ValueError, match="Formula not found"):
        TubeFeedCalculator(LocalFormulaCatalog()).find_formula(
            "unknown",
            package_type=PackageType.READY_TO_HANG,
        )


def test_find_formula_rejects_ambiguous_package_volume() -> None:
    with pytest.raises(ValueError, match="Multiple formulas matched") as error:
        TubeFeedCalculator(LocalFormulaCatalog()).find_formula(
            "jevity 1.2",
            package_type=PackageType.READY_TO_HANG,
        )
    assert "Choices:" in str(error.value)
    assert "ready_to_hang" in str(error.value)
    assert "kcal/mL" in str(error.value)


def test_existing_continuous_feeding_uses_documented_inputs() -> None:
    result = TubeFeedCalculator(LocalFormulaCatalog()).calculate_from_feeding(
        PersonEnteralFeeding(
            person_id=1,
            formula="Jevity 1.5",
            feeding_method=FeedingMethod.CONTINUOUS,
            rate_ml_hr=80,
            hours_per_day=16,
            flush_ml=250,
            flush_frequency_hours=6,
            package_type=PackageType.READY_TO_HANG,
            package_volume_ml=1000,
            caloric_density_kcal_ml=1.5,
            status=ClinicalStatus.ACTIVE,
            state_key="current-feeding",
            extracted_fact_id=1,
        ),
    )

    assert result.formula_volume_ml_day == 1280  # noqa: PLR2004
    assert result.formula_kcal_day == 1920  # noqa: PLR2004
    assert result.formula_protein_g_day == 81.7  # noqa: PLR2004
    assert result.formula_water_ml_day == 972.8  # noqa: PLR2004
    assert result.flush_water_ml_day == 1000  # noqa: PLR2004
    assert result.total_water_ml_day == 1972.8  # noqa: PLR2004


def test_existing_feeding_rejects_missing_schedule_inputs() -> None:
    feeding = PersonEnteralFeeding(
        person_id=1,
        formula="Jevity 1.5",
        feeding_method=FeedingMethod.CONTINUOUS,
        rate_ml_hr=80,
        package_type=PackageType.READY_TO_HANG,
        package_volume_ml=1000,
        caloric_density_kcal_ml=1.5,
        status=ClinicalStatus.ACTIVE,
        state_key="incomplete-feeding",
        extracted_fact_id=1,
    )

    with pytest.raises(ValueError, match="requires rate and hours per day"):
        TubeFeedCalculator(LocalFormulaCatalog()).calculate_from_feeding(feeding)


def _nutrient_amount(formula: Formula, nutrient_number: int) -> float:
    return next(
        nutrient.amount
        for nutrient in formula.nutrients
        if nutrient.number == nutrient_number
    )
