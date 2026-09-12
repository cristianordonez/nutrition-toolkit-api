from __future__ import annotations

import logging
import typing

from pydantic import BaseModel, Field

from ntk.controllers.base import BaseController
from ntk.controllers.session import controller_session
from ntk.models.base import ConsoleRenderableModel
from ntk.models.output import Output
from ntk.repositories.food_repo import FoodRepo
from ntk.services.calculators.tubefeed_calculator import (
    BolusFeedingSchedule,
    ContinuousFeedingSchedule,
    ProteinSupplementContribution,
    TubeFeedCalculator,
    TubeFeedResults,
)

logger = logging.getLogger(__name__)

if typing.TYPE_CHECKING:
    from sqlmodel import Session


class CalculateTubefeedOptions(BaseModel):
    """Options for Tubefeed workflow."""

    energy_needs: tuple[int, int] = Field(
        description="Manually set kcal range",
    )
    formula: str = Field(description="Name of formula")
    package_volume_ml: int | None = Field(
        description="Volume of formula package in mL",
        default=None,
    )
    n_hours: int = Field(
        description="Number of hours to run feed",
        default=18,
    )
    bolus: bool = Field(
        description="Calculate bolus feeding. Calculate continuous by default.",
        default=False,
    )
    n_bolus_feeds: int | None = Field(
        description="Number of daily feedings when bolus is enabled",
        default=None,
        gt=0,
    )
    feeding_route: str = Field(
        description="Enteral access route used to administer the formula",
        default="PEG",
        min_length=1,
    )
    start_time: str = Field(
        description="Time at which the feeding is hung",
        default="4pm",
        min_length=1,
    )
    starting_rate_ml_per_hr: int | None = Field(
        description="Optional initial continuous feeding rate in mL/hr",
        default=None,
        gt=0,
    )
    rate_increase_ml_per_hr: int | None = Field(
        description="Optional hourly rate advancement in mL/hr",
        default=None,
        gt=0,
    )
    protein_supplement_kcal: float = Field(
        description="Daily calories supplied by a protein supplement",
        default=0,
        ge=0,
    )
    protein_supplement_protein_g: float = Field(
        description="Daily protein supplied by a protein supplement in grams",
        default=0,
        ge=0,
    )
    protein_supplement_fluids_ml: float = Field(
        description="Daily fluid supplied by a protein supplement in mL",
        default=0,
        ge=0,
    )


class CalculateTubefeedResponse(ConsoleRenderableModel):
    """Response for CalculateTubefeed controller."""

    tubefeed_results: TubeFeedResults | None = Field(
        description="Results of tube feed calculation",
    )

    def to_console(self) -> str:
        """Render the calculated continuous or bolus tube-feed order."""
        result = self.tubefeed_results
        if result is None:
            return "No tube-feed recommendation was calculated."
        return result.to_console()


class CalculateTubefeedController(BaseController):
    """Handles running tubefeed command."""

    name = "calculate"
    help = "Calculate tubefeed recommendations"
    options_model = CalculateTubefeedOptions

    def __init__(self, session: Session | None = None) -> None:
        """Store the optional controller-owned session."""
        self.session = session

    def run(self, options: CalculateTubefeedOptions) -> Output:
        """Run tubefeed workflow.

        :param options: pydantic basemodel TubefeedOptions instance
        :return: Output model
        """
        output = CalculateTubefeedResponse(tubefeed_results=None)
        try:
            logger.debug("Options: %s", options)
            schedule = self._schedule(options)
            with controller_session(self.session) as session:
                tubefeed_results = TubeFeedCalculator(FoodRepo(session)).calculate(
                    energy_needs=options.energy_needs,
                    formula=options.formula,
                    package_volume_ml=options.package_volume_ml,
                    schedule=schedule,
                )
                output.tubefeed_results = tubefeed_results
                ec = 0
        except ValueError:
            logger.exception("Error calculating tubefeed")
            ec = 1
        return Output(
            controller=self.name,
            exit_code=ec,
            result=output,
        )

    @staticmethod
    def _schedule(
        options: CalculateTubefeedOptions,
    ) -> ContinuousFeedingSchedule | BolusFeedingSchedule:
        """Build the requested administration schedule."""
        protein_supplement = CalculateTubefeedController._protein_supplement(options)
        if options.bolus:
            if options.n_bolus_feeds is None:
                message = "Number of bolus feeds is required for bolus feeding."
                raise ValueError(message)
            return BolusFeedingSchedule(
                n_bolus_feeds=options.n_bolus_feeds,
                feeding_route=options.feeding_route,
                protein_supplement=protein_supplement,
            )
        return ContinuousFeedingSchedule(
            duration_hours=options.n_hours,
            feeding_route=options.feeding_route,
            start_time=options.start_time,
            starting_rate_ml_per_hr=options.starting_rate_ml_per_hr,
            rate_increase_ml_per_hr=options.rate_increase_ml_per_hr,
            protein_supplement=protein_supplement,
        )

    @staticmethod
    def _protein_supplement(
        options: CalculateTubefeedOptions,
    ) -> ProteinSupplementContribution | None:
        """Build an optional daily protein-supplement contribution."""
        values = (
            options.protein_supplement_kcal,
            options.protein_supplement_protein_g,
            options.protein_supplement_fluids_ml,
        )
        if not any(values):
            return None
        return ProteinSupplementContribution(
            kcal_per_day=options.protein_supplement_kcal,
            protein_per_day_g=options.protein_supplement_protein_g,
            fluids_per_day_ml=options.protein_supplement_fluids_ml,
        )
