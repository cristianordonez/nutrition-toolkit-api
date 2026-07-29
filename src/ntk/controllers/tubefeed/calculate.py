from __future__ import annotations

import logging
import typing

from pydantic import Field

from ntk.controllers.base import BaseController
from ntk.models.base import CustomBaseSettings
from ntk.models.output import Output
from ntk.repositories.formulas import OTHER_FORMULAS, READY_TO_HANG_FORMULAS

logger = logging.getLogger(__name__)

if typing.TYPE_CHECKING:
    from ntk.models.formula import Formula


class CalculateTubefeedOptions(CustomBaseSettings):
    """Options for Tubefeed workflow."""

    energy_needs: tuple[int, int] | None = Field(
        description="Manually set kcal range",
        default=None,
    )
    protein_needs: tuple[float, float] | None = Field(
        description="Manually set protein range",
        default=None,
    )
    formula: str = Field(description="Name of formula")
    density: float = Field(
        description="Caloric density of formula, usually 1.2 or 1.5",
        default=1.5,
    )
    bolus: bool = Field(
        description="Calculate bolus feeding. Calculate continuous by default.",
        default=False,
    )


class CalculateTubefeedResponse(CustomBaseSettings):
    """Response for CalculateTubefeed controller."""

    energy_needs: str


class CalculateTubefeedController(BaseController):
    """Handles running tubefeed command."""

    name = "calculate"
    help = "Calculate tubefeed recommendations"
    options_model = CalculateTubefeedOptions

    def run(self, options: CalculateTubefeedOptions) -> Output:
        """Run tubefeed workflow.

        :param options: pydantic basemodel TubefeedOptions instance
        :return: Output model
        """
        try:
            logger.debug("Options: %s", options)
            result = CalculateTubefeedResponse(energy_needs="")
            ec = 0
        except ValueError:
            ec = 1
        return Output(controller=self.name, exit_code=ec, result=result)

    @staticmethod
    def _get_formula_info(formula: str, density: float, *, bolus: bool) -> Formula:
        formula_name = formula + " " + str(density)
        if bolus:
            formula_info = OTHER_FORMULAS.get(formula_name)
        else:
            formula_info = READY_TO_HANG_FORMULAS.get(formula_name)
        if formula_info is None:
            msg = f"Formula not found {formula_info}"
            raise ValueError(msg)
        return formula_info
