"""Shared enums and helpers for person clinical domain records."""

from __future__ import annotations

import hashlib
import json
import typing
from datetime import UTC, datetime
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


def utc_now() -> datetime:
    """Return the current timezone-aware UTC application time."""
    return datetime.now(UTC)


def normalize_clinical_text(value: str | None) -> str | None:
    """Normalize source text used in deterministic clinical identities."""
    if value is None:
        return None
    normalized = " ".join(value.split()).casefold()
    return normalized or None


def _normalize_diet_phrase(value: str) -> str:
    """Normalize separators in one structured diet value."""
    normalized = (
        value.casefold().replace("&", " and ").replace("_", " ").replace("-", " ")
    )
    return " ".join(normalized.split())


def normalize_diet_type(value: str | None) -> str | None:
    """Return one canonical diet-type token for source-equivalent values."""
    if value is None:
        return None
    normalized = _normalize_diet_phrase(value)
    if not normalized:
        return None
    aliases = {
        "regular diet": "regular",
        "renal diet": "renal",
        "cardiac diet": "cardiac",
        "consistent carbohydrate": "ccd",
        "consistent carbohydrate diet": "ccd",
        "controlled carbohydrate": "ccd",
        "carbohydrate controlled": "ccd",
        "diabetic": "ccd",
        "diabetic diet": "ccd",
        "no added salt": "nas",
        "no added salt diet": "nas",
    }
    return aliases.get(normalized, normalized.replace(" ", "_"))


def normalize_diet_texture(value: str | None) -> str | None:
    """Return one canonical food-texture token for source-equivalent values."""
    if value is None:
        return None
    normalized = _normalize_diet_phrase(value)
    if not normalized:
        return None
    aliases = {
        "mechanical soft": "mechanical_soft",
        "mech soft": "mechanical_soft",
        "puree": "pureed",
        "soft and bite sized": "soft_and_bite_sized",
        "minced and moist": "minced_and_moist",
        "easy to chew": "easy_to_chew",
    }
    return aliases.get(normalized, normalized.replace(" ", "_"))


def normalize_diet_restriction(value: str) -> str:
    """Return one canonical diet-restriction token."""
    normalized = _normalize_diet_phrase(value)
    aliases = {
        "2 g na": "2_g_sodium",
        "2 gm na": "2_g_sodium",
        "2 gram sodium": "2_g_sodium",
        "2 grams sodium": "2_g_sodium",
        "low fat": "low_fat",
        "low cholesterol": "low_cholesterol",
        "no added salt": "nas",
    }
    return aliases.get(normalized, normalized.replace(" ", "_"))


def build_state_key(*parts: typing.Any) -> str:  # noqa: ANN401
    """Return a stable hash for one normalized clinical configuration."""
    payload = json.dumps(parts, default=str, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


__all__ = [
    "AppetiteLevel",
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
    "build_state_key",
    "normalize_clinical_text",
    "normalize_diet_restriction",
    "normalize_diet_texture",
    "normalize_diet_type",
    "utc_now",
]
