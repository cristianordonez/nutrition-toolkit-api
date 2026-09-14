from __future__ import annotations

from pydantic import BaseModel, Field

from ntk.models.extracted_fact_create import AIExtractedFactPayload  # noqa: TC001


class AIExtractedIdentity(BaseModel):
    """Identity clues explicitly present in source text."""

    source_person_name: str | None = None
    source_person_identifier: str | None = None
    facility_name: str | None = None
    facility_identifier: str | None = None


class AIExtractedFact(BaseModel):
    """One AI-eligible narrative clinical fact with extraction confidence."""

    payload: AIExtractedFactPayload = Field(discriminator="type")
    confidence: float = Field(
        ge=0.0,
        le=1.0,
    )
    confidence_reason: str | None = None


class AIUnknownDocumentFact(BaseModel):
    """Clinical fact plus identity clues from an unknown document."""

    identity: AIExtractedIdentity
    fact: AIExtractedFact
