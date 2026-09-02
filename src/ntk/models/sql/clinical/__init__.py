"""Canonical resident clinical domain models.

Weights, labs, and orders are deterministic-first because their source reports
have stable structure. Edema, meal intake, and wounds may also be populated
from typed AI payloads. ResidentClinicalFact is the narrative fallback for
observations and events without a dedicated domain model.
"""

from __future__ import annotations

from .clinical_fact import ClinicalFactType, ResidentClinicalFact
from .edema import ResidentEdema
from .lab import ResidentLab
from .meal_intake import ResidentMealIntake
from .order import ResidentOrder
from .weight import ResidentWeight
from .wound import ResidentWound

DETERMINISTIC_FIRST_MODELS = (ResidentWeight, ResidentLab, ResidentOrder)
AI_CAPABLE_STRUCTURED_MODELS = (
    ResidentEdema,
    ResidentMealIntake,
    ResidentWound,
)

__all__ = [
    "AI_CAPABLE_STRUCTURED_MODELS",
    "DETERMINISTIC_FIRST_MODELS",
    "ClinicalFactType",
    "ResidentClinicalFact",
    "ResidentEdema",
    "ResidentLab",
    "ResidentMealIntake",
    "ResidentOrder",
    "ResidentWeight",
    "ResidentWound",
]
