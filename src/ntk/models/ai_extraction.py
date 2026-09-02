from __future__ import annotations

from pydantic import BaseModel, Field

from ntk.models.extracted_fact_create import (
    ClinicalFactPayload,
    EdemaPayload,
    FactPayload,
    MealIntakePayload,
    WoundPayload,
)

AIClinicalFactPayload = (
    EdemaPayload | MealIntakePayload | WoundPayload | ClinicalFactPayload
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

    resident_name: str | None = None
    facility_resident_identifier: str | None = None
    facility_name: str | None = None


class AIUnknownDocumentFact(BaseModel):
    """Clinical fact plus identity clues from an unknown document."""

    identity: AIExtractedIdentity
    fact: AIExtractedFact
