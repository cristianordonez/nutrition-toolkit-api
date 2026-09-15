"""Stateless clinical calculators that run entirely on-device.

``NutritionCalculator`` (BMI/energy needs) has no local-data dependency and
is dual-use, so it lives in ``ntk.calculators.nutrition_calculator`` instead
-- both apps import it from there.
"""

from __future__ import annotations

from .parenteral_nutrition_calculator import (
    ParenteralNutritionCalculationInput,
    ParenteralNutritionCalculator,
)
from .tubefeed_calculator import (
    BolusFeedingSchedule,
    ContinuousFeedingSchedule,
    FeedingSchedule,
    FreeWaterFlush,
    ProteinSupplementContribution,
    TubeFeedCalculator,
    TubeFeedDailyTotals,
    TubeFeedResults,
)
from .weight_history_calculator import WeightHistoryCalculator

__all__ = [
    "BolusFeedingSchedule",
    "ContinuousFeedingSchedule",
    "FeedingSchedule",
    "FreeWaterFlush",
    "ParenteralNutritionCalculationInput",
    "ParenteralNutritionCalculator",
    "ProteinSupplementContribution",
    "TubeFeedCalculator",
    "TubeFeedDailyTotals",
    "TubeFeedResults",
    "WeightHistoryCalculator",
]
