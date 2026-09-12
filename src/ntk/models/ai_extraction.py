from __future__ import annotations

from pydantic import BaseModel, Field

from ntk.models.extracted_fact_create import (
    AllergyPayload,
    AppetitePayload,
    ClinicalFactPayload,
    DiagnosisPayload,
    DialysisPayload,
    EdemaPayload,
    FactPayload,
    FoodPreferencePayload,
    GIObservationPayload,
    MealIntakePayload,
    NutritionGoalPayload,
    OralFeedingStatusPayload,
    WoundPayload,
)

AIClinicalFactPayload = (
    AllergyPayload
    | AppetitePayload
    | ClinicalFactPayload
    | DiagnosisPayload
    | DialysisPayload
    | EdemaPayload
    | FoodPreferencePayload
    | GIObservationPayload
    | MealIntakePayload
    | OralFeedingStatusPayload
    | NutritionGoalPayload
    | WoundPayload
)


class AIExtractedFact(BaseModel):
    """One clinical fact identified by the AI."""

    payload: FactPayload
    confidence: float = Field(
        ge=0.0,
        le=1.0,
    )
    confidence_reason: str | None = None


class AIExtractedClinicalFact(BaseModel):
    """One AI-extracted fact not owned by a dedicated report extractor."""

    payload: AIClinicalFactPayload = Field(discriminator="type")
    confidence: float = Field(
        ge=0.0,
        le=1.0,
    )
    confidence_reason: str | None = None


class AIExtractedIdentity(BaseModel):
    """Identity clues explicitly present in source text."""

    source_person_name: str | None = None
    source_person_identifier: str | None = None
    facility_name: str | None = None
    facility_identifier: str | None = None


class AIUnknownDocumentFact(BaseModel):
    """Clinical fact plus identity clues from an unknown document."""

    identity: AIExtractedIdentity
    fact: AIExtractedFact
