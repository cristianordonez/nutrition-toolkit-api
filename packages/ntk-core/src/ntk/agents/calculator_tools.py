"""Nutrition calculation tools."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic_ai import FunctionToolset

from ntk.calculators.nutrition_calculator import NutritionCalculator


@dataclass(frozen=True)
class CalculatorToolDependencies:
    """No runtime dependencies are required by calculation tools."""


CALCULATOR_TOOLSET = FunctionToolset[CalculatorToolDependencies](id="calculators")
CALCULATOR_TOOLSET.add_function(
    NutritionCalculator.calculate,
    name="calculate_nutrition_needs",
    description=(
        "Calculate a complete nutrition-needs profile only when current weight, "
        "height, age, and normalized equation sex are documented, the applicable "
        "result is not already in person.derived_calculations, and "
        "clinical evidence requires selecting factors. Supply the clinically "
        "selected factors; never multiply them yourself."
    ),
)

__all__ = [
    "CALCULATOR_TOOLSET",
    "CalculatorToolDependencies",
]
