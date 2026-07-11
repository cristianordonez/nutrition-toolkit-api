from __future__ import annotations

# ruff: noqa: S101,SLF001
import pytest

from ntk.controllers.calculate.tubefeed import TubefeedController, TubefeedOptions
from ntk.repositories.formulas import OTHER_FORMULAS, READY_TO_HANG_FORMULAS


def test_tubefeed_run_returns_success_output() -> None:
    options = TubefeedOptions(formula="jevity", density=1.5)
    output = TubefeedController().run(options)

    assert output.controller == "tubefeed"
    assert output.exit_code == 0
    assert output.result == {}


def test_get_formula_info_returns_ready_to_hang_formula() -> None:
    formula = TubefeedController._get_formula_info("jevity", 1.2, bolus=False)

    assert formula.name == "jevity 1.2"
    assert formula.consistency == "nectar"
    assert formula.nutrition.cal == READY_TO_HANG_FORMULAS["jevity 1.2"].nutrition.cal


def test_get_formula_info_returns_other_formula_for_bolus() -> None:
    formula = TubefeedController._get_formula_info("jevity", 1.2, bolus=True)

    assert formula.name == "jevity 1.2"
    assert formula.consistency == "nectar"
    assert formula.nutrition.cal == OTHER_FORMULAS["jevity 1.2"].nutrition.cal


def test_get_formula_info_raises_for_unknown_formula() -> None:
    with pytest.raises(ValueError, match="Formula not found"):
        TubefeedController._get_formula_info("unknown", 1.2, bolus=False)
