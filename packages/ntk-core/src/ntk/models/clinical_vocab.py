"""Clinical vocabulary enums shared across apps.

Used by both engine's SQLModel tables and the table-less NCP-context DTOs
that mirror them for the wire contract with cloud-api.
"""

from __future__ import annotations

from enum import StrEnum


class ClinicalStatus(StrEnum):
    """Lifecycle state explicitly supported by a clinical source."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    HISTORICAL = "historical"
    UNKNOWN = "unknown"


class FeedingMethod(StrEnum):
    """Supported enteral-feeding delivery methods."""

    CONTINUOUS = "continuous"
    CYCLIC = "cyclic"
    BOLUS = "bolus"
    UNKNOWN = "unknown"


class ParenteralAccessRoute(StrEnum):
    """Documented vascular access category for parenteral nutrition."""

    CENTRAL = "central"
    PERIPHERAL = "peripheral"
    UNKNOWN = "unknown"


class ParenteralFormulaType(StrEnum):
    """Source-supported parenteral nutrition formula category."""

    STANDARD = "standard"
    CONCENTRATED = "concentrated"
    CUSTOM = "custom"
    UNKNOWN = "unknown"


class LipidDeliveryType(StrEnum):
    """How intravenous lipids are delivered with a PN prescription."""

    INCLUDED = "included"
    PIGGYBACK = "piggyback"
    NONE = "none"
    UNKNOWN = "unknown"


class ParenteralNutritionStatus(StrEnum):
    """Lifecycle state explicitly documented for parenteral nutrition."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    HISTORICAL = "historical"
    UNKNOWN = "unknown"


class AppetiteLevel(StrEnum):
    """Controlled subjective appetite observation values."""

    VERY_POOR = "very_poor"
    POOR = "poor"
    FAIR = "fair"
    GOOD = "good"
    EXCELLENT = "excellent"
    UNKNOWN = "unknown"


class GISymptom(StrEnum):
    """Nutrition-relevant gastrointestinal symptoms."""

    NAUSEA = "nausea"
    VOMITING = "vomiting"
    DIARRHEA = "diarrhea"
    CONSTIPATION = "constipation"
    ABDOMINAL_PAIN = "abdominal_pain"
    EARLY_SATIETY = "early_satiety"
    BLOATING = "bloating"
    REFLUX = "reflux"
    OTHER = "other"


class DialysisType(StrEnum):
    """Nutrition-relevant dialysis modalities."""

    HEMODIALYSIS = "hemodialysis"
    PERITONEAL_DIALYSIS = "peritoneal_dialysis"
    OTHER = "other"
    UNKNOWN = "unknown"


class DentitionStatus(StrEnum):
    """Broad person dentition states relevant to oral intake."""

    NATURAL = "natural"
    PARTIAL_DENTITION = "partial_dentition"
    EDENTULOUS = "edentulous"
    DENTURES = "dentures"
    UNKNOWN = "unknown"


class DentureStatus(StrEnum):
    """Availability or use of an upper or lower denture."""

    PRESENT = "present"
    ABSENT = "absent"
    PARTIAL = "partial"
    NOT_WORN = "not_worn"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


class FoodPreferenceType(StrEnum):
    """Kind of person food-service preference."""

    FOOD = "food"
    BEVERAGE = "beverage"
    CUISINE = "cuisine"
    MEAL_PATTERN = "meal_pattern"
    DIETARY_PRACTICE = "dietary_practice"
    OTHER = "other"


class FoodPreferenceValue(StrEnum):
    """Person preference or requirement for an item."""

    LIKES = "likes"
    DISLIKES = "dislikes"
    PREFERS = "prefers"
    AVOIDS = "avoids"
    REQUIRES = "requires"


class FoodPreferenceReason(StrEnum):
    """Documented reason for a food preference."""

    PERSONAL = "personal"
    CULTURAL = "cultural"
    RELIGIOUS = "religious"
    ETHICAL = "ethical"
    OTHER = "other"
    UNKNOWN = "unknown"


class NutritionGoalType(StrEnum):
    """Supported source-documented nutrition goal categories."""

    WEIGHT_GAIN = "weight_gain"
    WEIGHT_MAINTENANCE = "weight_maintenance"
    WEIGHT_LOSS = "weight_loss"
    INCREASE_PROTEIN = "increase_protein"
    INCREASE_CALORIES = "increase_calories"
    INCREASE_FLUID = "increase_fluid"
    FLUID_RESTRICTION = "fluid_restriction"
    IMPROVE_MEAL_INTAKE = "improve_meal_intake"
    INCREASE_FIBER = "increase_fiber"
    REDUCE_SODIUM = "reduce_sodium"
    OTHER = "other"


class WeightContext(StrEnum):
    """Documented context in which a body weight was obtained or specified."""

    ROUTINE = "routine"
    PRE_DIALYSIS = "pre_dialysis"
    POST_DIALYSIS = "post_dialysis"
    DRY_WEIGHT = "dry_weight"
    TARGET_WEIGHT = "target_weight"
    UNKNOWN = "unknown"


class ClinicalFactType(StrEnum):
    """Classify a person clinical fact as an observation or event."""

    OBSERVATION = "observation"
    EVENT = "event"


__all__ = [
    "AppetiteLevel",
    "ClinicalFactType",
    "ClinicalStatus",
    "DentitionStatus",
    "DentureStatus",
    "DialysisType",
    "FeedingMethod",
    "FoodPreferenceReason",
    "FoodPreferenceType",
    "FoodPreferenceValue",
    "GISymptom",
    "LipidDeliveryType",
    "NutritionGoalType",
    "ParenteralAccessRoute",
    "ParenteralFormulaType",
    "ParenteralNutritionStatus",
    "WeightContext",
]
