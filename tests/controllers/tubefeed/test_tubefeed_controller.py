# Copyright 2026, Cristian Ordonez

from __future__ import annotations

# ruff: noqa: SLF001
import pytest

from ntk.controllers.tubefeed.calculate import (
    CalculateTubefeedController,
    CalculateTubefeedOptions,
    CalculateTubefeedResponse,
)
from ntk.repositories.formula_repo import OTHER_FORMULAS, READY_TO_HANG_FORMULAS


def test_tubefeed_run_returns_success_output() -> None:
    options = CalculateTubefeedOptions(formula="jevity", density=1.5)
    output = CalculateTubefeedController().run(options)
    assert output.controller == "calculate"
    assert output.exit_code == 0
    assert isinstance(output.result, CalculateTubefeedResponse)


def test_get_formula_info_returns_ready_to_hang_formula() -> None:
    formula = CalculateTubefeedController._get_formula_info("jevity", 1.2, bolus=False)
    assert formula.name == "jevity 1.2"
    assert formula.consistency == "nectar"
    assert formula.nutrition.cal == READY_TO_HANG_FORMULAS["jevity 1.2"].nutrition.cal


def test_get_formula_info_returns_other_formula_for_bolus() -> None:
    formula = CalculateTubefeedController._get_formula_info("jevity", 1.2, bolus=True)
    assert formula.name == "jevity 1.2"
    assert formula.consistency == "nectar"
    assert formula.nutrition.cal == OTHER_FORMULAS["jevity 1.2"].nutrition.cal


def test_get_formula_info_raises_for_unknown_formula() -> None:
    with pytest.raises(ValueError, match="Formula not found"):
        CalculateTubefeedController._get_formula_info("unknown", 1.2, bolus=False)
