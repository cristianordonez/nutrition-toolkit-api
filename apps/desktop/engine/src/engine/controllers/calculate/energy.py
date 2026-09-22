"""Calculate daily nutrition needs from measurements typed in directly.

Ad hoc: nothing is read from or written to the local database. The same
calculator backs the NCP agent's ``calculate_nutrition_needs`` tool, so a
number worked out here matches what a generated note would use.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ntk.calculators.nutrition_calculator import (
    EnergyNeedsInput,
    EnergyNeedsResult,
    Gender,
    Goal,
    NutritionCalculator,
)
from ntk.controllers.base import BaseController
from ntk.models.base import ConsoleRenderableModel
from ntk.models.output import Output


class EnergyOptions(BaseModel):
    """Measurements for one nutrition-needs calculation."""

    weight: float = Field(description="Weight in lbs", gt=0)
    height: float = Field(description="Height in inches", gt=0)
    age: int = Field(description="Age in years", gt=0, le=120)
    gender: str = Field(default="f", description="Equation category: m or f")
    goal: str = Field(default="maintain", description="lose, maintain, or gain")
    activity_level: float = Field(default=1.2, description="Multiplier, 1.2-1.9")
    dialysis: bool = Field(default=False, description="Receiving hemodialysis")
    amputation: float | None = Field(
        default=None,
        description="Percent of body weight lost to amputation",
    )


class EnergyResult(ConsoleRenderableModel):
    """The calculated nutrition-needs profile."""

    needs: EnergyNeedsResult

    def to_console(self) -> str:
        """Render the profile as formatted JSON."""
        return self.model_dump_json(indent=2)


class EnergyController(BaseController):
    """Calculate calorie, protein, and fluid needs."""

    name = "energy"
    help = "Calculate daily calorie, protein, and fluid needs"
    options_model = EnergyOptions

    def run(self, options: EnergyOptions) -> Output[EnergyResult]:
        """Return the nutrition-needs profile for the supplied measurements."""
        needs = NutritionCalculator.calculate(
            EnergyNeedsInput(
                height_in=options.height,
                weight_lb=options.weight,
                gender=Gender(options.gender),
                age=options.age,
                activity_level=options.activity_level,
                amputation_percent=options.amputation,
                goal=Goal(options.goal),
                dialysis=options.dialysis,
            ),
        )
        return Output(
            result=EnergyResult(needs=needs),
            controller=self.name,
            exit_code=0,
        )


__all__ = ["EnergyController", "EnergyOptions", "EnergyResult"]
