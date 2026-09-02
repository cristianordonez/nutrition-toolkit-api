"""Model used to created ExtractedFact."""

from __future__ import annotations

import typing
from datetime import date, datetime  # noqa: TC003

from pydantic import BaseModel, ConfigDict, Field


class WeightPayload(BaseModel):
    type: typing.Literal["weight"] = "weight"
    weight_lb: float
    measured_at: datetime | None = None
    description: str | None = None


class LabPayload(BaseModel):
    type: typing.Literal["lab"] = "lab"
    name: str
    result: str
    unit: str | None = None
    reference_range: str | None = None
    flag: str | None = None
    observed_at: datetime


class OrderPayload(BaseModel):
    type: typing.Literal["order"] = "order"
    summary: str
    category: str | None = None
    status: str | None = None
    revision_date: date | None = None
    supply_last_order_date: date | None = None
    supply_reorder: str | None = None


class EdemaPayload(BaseModel):
    type: typing.Literal["edema"] = "edema"
    location: str | None = None
    severity: str | None = None
    observed_at: datetime


class WoundPayload(BaseModel):
    type: typing.Literal["wound"] = "wound"
    wound_number: str | None = None
    wound_type: str
    location: str | None = None
    weeks_in_treatment: int | None = None
    progress: str | None = None
    stage: str | None = None
    size: str | None = None
    assessment_note: str | None = None
    physician_orders: str | None = None
    physician_orders_notes: str | None = None
    observed_at: datetime | None = None


class MealIntakePayload(BaseModel):
    type: typing.Literal["intake"] = "intake"
    min_percent: float | None = None
    max_percent: float | None = None
    appetite: str | None = None
    observed_at: datetime


class ClinicalFactPayload(BaseModel):
    """Narrative clinical observation or event without a dedicated table."""

    type: typing.Literal["clinical_fact"] = "clinical_fact"
    clinical_fact_type: typing.Literal["observation", "event"]
    observation_type: str
    status: str | None = None
    severity: str | None = None
    description: str | None = None
    observed_at: datetime


class KnowledgeChunkPayload(BaseModel):
    type: typing.Literal["knowledge_chunk"] = "knowledge_chunk"
    content: str
    chunk_index: int
    knowledge_type: str


FactPayload = typing.Annotated[
    WeightPayload
    | LabPayload
    | EdemaPayload
    | WoundPayload
    | OrderPayload
    | MealIntakePayload
    | ClinicalFactPayload
    | KnowledgeChunkPayload,
    Field(discriminator="type"),
]


class ExtractedFactCreate(BaseModel):
    """Transient extracted fact used to create a persisted ExtractedFact."""

    model_config = ConfigDict(extra="forbid")

    payload: FactPayload
    confidence: float = Field(ge=0.0, le=1.0)
    confidence_reason: str | None = None
    model_name: str | None = None
    # unresolved identity clues
    facility_resident_identifier: str | None = None
    resident_name: str | None = None
    facility_name: str | None = None
    date_of_birth: date | None = None
    sex: str | None = None
    height_in: float | None = Field(default=None, gt=0)

    # already known identity
    resident_id: int | None = None
    facility_id: int | None = None
    resident_facility_stay_id: int | None = None
    progress_note_id: int | None = None

    source_page: int | None = Field(default=None, ge=1)
