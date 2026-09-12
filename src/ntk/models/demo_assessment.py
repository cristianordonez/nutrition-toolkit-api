"""Public response models for the end-to-end assessment demo."""

# Pydantic resolves these response annotation types at runtime.
# ruff: noqa: TC001, TC003

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

from ntk.models.person_detail import PersonDetail
from ntk.models.sql.person import AssessmentSource, StatusType


class DemoPersonSummary(BaseModel):
    """Optional person metadata observed in the transient upload facts."""

    id: int | None = None
    name: str
    person_identifier: str | None = None
    date_of_birth: date | None = None
    facility_id: int | None = None
    facility_name: str | None = None

    @classmethod
    def from_detail(cls, detail: PersonDetail) -> DemoPersonSummary:
        """Create an identity summary without requiring a persisted person."""
        return cls(
            id=detail.person_id,
            name=detail.name,
            person_identifier=detail.person_identifier,
            date_of_birth=detail.date_of_birth,
            facility_id=detail.facility_id,
            facility_name=detail.facility.name if detail.facility else None,
        )


class DemoDocumentIngestionSummary(BaseModel):
    """Observable transient extraction results for one uploaded document."""

    document_id: int | None = None
    document_type: str | None = None
    already_ingested: bool = False
    facts_extracted: int = Field(ge=0)
    facts_persisted: int = Field(ge=0)


class DemoIngestionSummary(BaseModel):
    """Combined transient extraction results for every uploaded document."""

    documents: list[DemoDocumentIngestionSummary] = Field(default_factory=list)
    document_id: int | None = None
    document_type: str | None = None
    already_ingested: bool = False
    facts_extracted: int = Field(ge=0)
    facts_persisted: int = Field(ge=0)


class DemoContextSummary(BaseModel):
    """Deterministic measurements from assessment-context budgeting."""

    raw_token_count: int = Field(ge=0)
    final_token_count: int = Field(ge=0)
    tokens_removed: int = Field(ge=0)
    token_reduction_percent: float = Field(ge=0, le=100)
    omitted_record_counts: dict[str, int] = Field(default_factory=dict)


class DemoGeneratedAssessment(BaseModel):
    """Generated but intentionally unpersisted demo assessment."""

    id: int | None = None
    person_id: int | None = None
    content: str
    assessment_source: AssessmentSource
    assessment_date: date
    created_by: str
    status: StatusType
    model_name: str | None = None
    created_at: datetime

    @classmethod
    def from_content(
        cls,
        content: str,
        *,
        person_id: int | None,
        model_name: str,
        created_at: datetime,
    ) -> DemoGeneratedAssessment:
        """Build the response without creating a PersonAssessment database row."""
        return cls(
            person_id=person_id,
            content=content,
            assessment_source=AssessmentSource.GENERATED,
            assessment_date=created_at.date(),
            created_by=model_name,
            status=StatusType.DRAFT,
            model_name=model_name,
            created_at=created_at,
        )


class DemoAssessmentResponse(BaseModel):
    """Result of combining documents into one generated person assessment."""

    ingestion: DemoIngestionSummary
    person: DemoPersonSummary
    detail: PersonDetail
    context: DemoContextSummary
    assessment: DemoGeneratedAssessment


__all__ = [
    "DemoAssessmentResponse",
    "DemoContextSummary",
    "DemoDocumentIngestionSummary",
    "DemoGeneratedAssessment",
    "DemoIngestionSummary",
    "DemoPersonSummary",
]
