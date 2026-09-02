"""Generate assessments for persisted residents."""

from __future__ import annotations

import typing
from datetime import date, datetime  # noqa: TC003 - Pydantic resolves at runtime

from pydantic import BaseModel, Field

from ntk.controllers.base import BaseController
from ntk.controllers.session import controller_session
from ntk.models.output import Output
from ntk.models.sql.resident import (
    AssessmentSource,  # noqa: TC001 - Pydantic resolves this type at runtime
    ResidentAssessment,  # noqa: TC001 - used to build the response at runtime
    StatusType,  # noqa: TC001 - Pydantic resolves this type at runtime
)
from ntk.repositories.assessment_repo import AssessmentRepo
from ntk.repositories.embedding_repo import EmbeddingRepo
from ntk.repositories.resident_repo import ResidentRepo
from ntk.services.assessment import AssessmentGenerationService

if typing.TYPE_CHECKING:
    from sqlmodel import Session


class ResidentAssessmentGenerationOptions(BaseModel):
    """One resident and their optional assessment guidance."""

    resident_identifier: str = Field(min_length=1)
    facility_id: str | None = Field(default=None, min_length=1)
    context: str | None = None


class AssessmentGenerationOptions(BaseModel):
    """Resident-specific assessment generation requests."""

    residents: list[ResidentAssessmentGenerationOptions] = Field(min_length=1)


class GeneratedResidentAssessment(BaseModel):
    """Generated assessment enriched with its resident's display name."""

    id: int | None
    resident_id: int
    resident_name: str
    resident_facility_stay_id: int | None
    source_progress_note_id: int | None
    content: str
    assessment_source: AssessmentSource
    source_filename: str | None
    content_hash: str
    assessment_index: int
    assessment_date: date
    created_by: str
    status: StatusType
    model_name: str | None
    created_at: datetime
    finalized_at: datetime | None

    @classmethod
    def from_assessment(
        cls,
        assessment: ResidentAssessment,
    ) -> GeneratedResidentAssessment:
        """Build an API result from an assessment with its resident loaded."""
        return cls(
            **assessment.model_dump(),
            resident_name=assessment.resident.name,
        )


class AssessmentGenerationResult(BaseModel):
    """Assessments created by one generation request."""

    assessments: list[GeneratedResidentAssessment]


class AssessmentGenerationController(BaseController):
    """Generate and persist assessments for requested residents."""

    name = "generate"
    help = "Generate resident assessments"
    options_model = AssessmentGenerationOptions

    def __init__(self, session: Session | None = None) -> None:
        """Store the optional controller-owned session."""
        self.session = session

    async def run(
        self,
        options: AssessmentGenerationOptions,
    ) -> Output[AssessmentGenerationResult]:
        """Generate assessments in request order using one session."""
        assessments: list[GeneratedResidentAssessment] = []
        seen: set[tuple[str | None, str]] = set()
        with controller_session(self.session) as session:
            resident_repository = ResidentRepo(session)
            service = AssessmentGenerationService(
                resident_repository,
                AssessmentRepo(session),
                EmbeddingRepo(session),
            )
            for request in options.residents:
                resident_key = (
                    request.facility_id,
                    request.resident_identifier,
                )
                if resident_key in seen:
                    continue
                seen.add(resident_key)
                assessment = await service.generate(
                    request.resident_identifier,
                    facility_id=request.facility_id,
                    context=request.context,
                )
                assessments.append(
                    GeneratedResidentAssessment.from_assessment(assessment),
                )
        return Output(
            result=AssessmentGenerationResult(assessments=assessments),
            controller=self.name,
            exit_code=0,
        )


__all__ = [
    "AssessmentGenerationController",
    "AssessmentGenerationOptions",
    "AssessmentGenerationResult",
    "GeneratedResidentAssessment",
    "ResidentAssessmentGenerationOptions",
]
