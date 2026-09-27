"""Result shapes for a nutrition-needs calculation.

These live in ``models`` rather than beside the calculator that produces them
because both sides of the calculator split need them. ``engine.services.
calculators.nutrition_calculator`` returns an ``EnergyNeedsResult``, and
``engine.models.derived_calculations`` carries one on the person snapshot --
so defining them with the calculator made the models package import the
calculators package, which imports the models package back.

Data shapes with no behaviour, which is what these are, belong here anyway.
"""

from __future__ import annotations

from pydantic import BaseModel


class RangeResult(BaseModel):
    """Named low and high values for a calculated factor range."""

    low: float
    high: float


class EnergyNeedsResult(BaseModel):
    """Structured outputs from a complete nutrition-needs calculation."""

    bmi: float
    bmi_category: str
    current_weight_lb: float
    ideal_weight_lb: float
    adjusted_weight_lb: float
    calculation_weight_lb: float
    calculation_weight_kg: float
    weight_basis: str
    calorie_factor: RangeResult
    protein_factor: RangeResult
    fluid_factor: RangeResult
    calories_kcal_day: RangeResult
    protein_g_day: RangeResult
    fluids_ml_day: RangeResult
    mifflin_kcal_day: float


__all__ = ["EnergyNeedsResult", "RangeResult"]
