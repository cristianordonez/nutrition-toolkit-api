from __future__ import annotations

import json
import typing
from datetime import datetime  # noqa: TC003
from enum import StrEnum

from pydantic import BaseModel, Field

from ntk.models.sql.resident import (
    LabResult,
    MedicationData,
    Resident,
    ResidentSnapshot,
    SupplementData,
    TubeFeedingData,
    WeightHistoryEntry,
    WoundData,
)


class ResidentDocumentType(StrEnum):
    """Identify resident-report formats used for structured extraction."""

    PCC_PROGRESS_REPORT = "pcc-progress-report"
    PCC_WEIGHT_HISTORY_REPORT = "pcc-weight-history-report"
    PCC_ORDER_LIST_REPORT = "pcc-order-list-report"
    PCC_WEIGHT_VITALS_SUMMARY = "pcc-weight-vitals-summary"


class SourceReference(BaseModel):
    source_type: str
    page_start: int | None = None
    page_end: int | None = None
    extracted_at: datetime
    source_name: str | None = None


class ProgressNote(BaseModel):
    note_date: datetime | None = None
    note_type: str | None = None
    author: str | None = None
    note_text: str
    source: SourceReference
    raw_text: str


class WeightVitalsExtraction(BaseModel):
    """Structured facts extracted from a PCC weights-and-vitals report."""

    source: SourceReference
    facility_id: str | None = None
    height: float | None = None
    date_of_birth: str | None = None
    age: int | None = None
    weight_history: list[WeightHistoryEntry] = Field(default_factory=list)


class LabReportExtraction(BaseModel):
    """Structured facts extracted from a PCC lab results report."""

    source: SourceReference
    facility_id: str | None = None
    latest_labs: list[LabResult] = Field(default_factory=list)
    latest_labs_date: str | None = None


class ResidentWoundData(BaseModel):
    """Wounds listed for one resident in a wound report."""

    facility_id: str
    resident_name: str | None = None
    wounds: list[WoundData] = Field(default_factory=list)


class WoundReportExtraction(BaseModel):
    """Structured facts extracted from a wound report."""

    source: SourceReference
    residents: list[ResidentWoundData] = Field(default_factory=list)


class PccOrder(BaseModel):
    """One row from a PCC order listing report."""

    resident_name: str | None = None
    order_summary: str
    order_category: str | None = None
    order_status: str | None = None
    revision_date: str | None = None
    supply_last_order_date: str | None = None
    supply_reorder: str | None = None


class OrderReportExtraction(BaseModel):
    """Structured facts extracted from a PCC order listing report."""

    source: SourceReference
    facility_id: str | None = None
    orders: list[PccOrder] = Field(default_factory=list)
    medications: list[MedicationData] = Field(default_factory=list)
    diet: str | None = None
    diet_texture: str | None = None
    liquid_consistency: str | None = None
    supplements: list[SupplementData] = Field(default_factory=list)
    tubefeed_order: TubeFeedingData | None = None


class ClinicalEventType(StrEnum):
    WEIGHT = "weight"
    LAB = "lab"
    DIET_CHANGE = "diet_change"
    MEDICATION_CHANGE = "medication_change"
    WOUND = "wound"
    HOSPITALIZATION = "hospitalization"
    INTAKE = "intake"
    TUBE_FEEDING = "tube_feeding"
    OTHER = "other"


class ClinicalEvent(BaseModel):
    event_type: ClinicalEventType
    occurred_at: datetime | None = None
    description: str
    structured_data: dict[str, typing.Any] = Field(default_factory=dict)
    sources: list[SourceReference] = Field(default_factory=list)


class SourcedValue(BaseModel):
    value: typing.Any
    observed_at: datetime | None = None
    sources: list[SourceReference] = Field(default_factory=list)


class DataConflict(BaseModel):
    field: str
    values: list[SourcedValue]
    explanation: str


class ResidentContext(BaseModel):
    """Non-persisted resident identity, clinical snapshot, and provenance."""

    resident_info: Resident | None = None
    resident_snapshot: ResidentSnapshot = Field(default_factory=ResidentSnapshot)
    previous_snapshot: ResidentSnapshot | None = None
    latest_nutrition_assessment: ProgressNote | None = None
    progress_notes: list[ProgressNote] = Field(default_factory=list)
    clinical_events: list[ClinicalEvent] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    conflicts: list[DataConflict] = Field(default_factory=list)

    def clinical_payload(self) -> dict[str, object]:
        """Return context without snapshot persistence implementation details."""
        return self.model_dump(
            mode="json",
            exclude={
                "resident_info": {"created_at"},
                "resident_snapshot": {"id", "resident_id", "created_at"},
                "previous_snapshot": {"id", "resident_id", "created_at"},
            },
        )

    def to_console(self) -> str:
        """Render the complete extracted context as formatted JSON."""
        return json.dumps(self.clinical_payload(), indent=2)
