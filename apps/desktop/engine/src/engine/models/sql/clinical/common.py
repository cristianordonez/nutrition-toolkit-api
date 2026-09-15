"""Shared helpers for person clinical domain records.

The clinical vocabulary enums used across these tables live in
``ntk.models.clinical_vocab`` since cloud-api's table-less NCP-context DTOs
need the same vocabulary; they are re-exported here so existing
``from .common import ClinicalStatus`` imports keep working unchanged.
"""

from __future__ import annotations

import hashlib
import json
import typing
from datetime import UTC, datetime

from ntk.models.clinical_vocab import (
    AppetiteLevel,
    ClinicalStatus,
    DentitionStatus,
    DentureStatus,
    DialysisType,
    FeedingMethod,
    FoodPreferenceReason,
    FoodPreferenceType,
    FoodPreferenceValue,
    GISymptom,
    LipidDeliveryType,
    NutritionGoalType,
    ParenteralAccessRoute,
    ParenteralFormulaType,
    ParenteralNutritionStatus,
    WeightContext,
)


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
