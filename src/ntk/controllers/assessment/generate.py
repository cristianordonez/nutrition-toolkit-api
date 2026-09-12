"""Generate assessments for persisted persons."""

from __future__ import annotations

import typing
from datetime import date, datetime  # noqa: TC003 - Pydantic resolves at runtime

from pydantic import AliasChoices, BaseModel, Field

from ntk.controllers.base import BaseController
from ntk.controllers.session import controller_session
from ntk.models.output import Output
from ntk.models.sql.person import (
    AssessmentSource,  # noqa: TC001 - Pydantic resolves this type at runtime
    PersonAssessment,  # noqa: TC001 - used to build the response at runtime
    StatusType,  # noqa: TC001 - Pydantic resolves this type at runtime
)
from ntk.pipelines.assessment import AssessmentPipeline
from ntk.repositories.assessment_repo import AssessmentRepo
from ntk.repositories.embedding_repo import EmbeddingRepo
from ntk.repositories.facility_repo import FacilityRepo
from ntk.repositories.food_repo import FoodRepo
from ntk.repositories.person_repo import PersonRepo
from ntk.services.calculators.tubefeed_calculator import TubeFeedCalculator
from ntk.services.facility_resolver import FacilityResolver
from ntk.services.person.detail_builder import PersonDetailBuilder
from ntk.services.person.person_service import PersonService

if typing.TYPE_CHECKING:
    from sqlmodel import Session


class PersonAssessmentGenerationOptions(BaseModel):
    """One person and their optional assessment guidance."""

    source_person_identifier: str = Field(min_length=1)
    source_system: str = Field(default="pointclickcare", min_length=1)
    facility_identifier: str | None = Field(
        default=None,
        min_length=1,
        validation_alias=AliasChoices("facility_identifier", "facility_id"),
    )
    context: str | None = None


class AssessmentGenerationOptions(BaseModel):
    """Person-specific assessment generation requests."""

    persons: list[PersonAssessmentGenerationOptions] = Field(min_length=1)


class GeneratedPersonAssessment(BaseModel):
    """Generated assessment enriched with its person's display name."""

    id: int | None
    person_id: int
    person_name: str
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
        assessment: PersonAssessment,
    ) -> GeneratedPersonAssessment:
        """Build an API result from an assessment with its person loaded."""
        return cls(
            **assessment.model_dump(),
            person_name=assessment.person.name,
        )


class AssessmentGenerationResult(BaseModel):
    """Assessments created by one generation request."""

    assessments: list[GeneratedPersonAssessment]

    @classmethod
    def from_assessments(
        cls,
        assessments: typing.Iterable[PersonAssessment],
    ) -> AssessmentGenerationResult:
        """Build the shared HTTP/CLI projection for generated assessments."""
        return cls(
            assessments=[
                GeneratedPersonAssessment.from_assessment(assessment)
                for assessment in assessments
            ],
        )


class AssessmentGenerationController(BaseController):
    """Generate and persist assessments for requested persons."""

    name = "generate"
    help = "Generate person assessments"
    options_model = AssessmentGenerationOptions

    def __init__(self, session: Session | None = None) -> None:
        """Store the optional controller-owned session."""
        self.session = session

    async def run(
        self,
        options: AssessmentGenerationOptions,
    ) -> Output[AssessmentGenerationResult]:
        """Generate assessments in request order using one session."""
        with controller_session(self.session) as session:
            facility_resolver = FacilityResolver(FacilityRepo(session))
            food_repository = FoodRepo(session)
            pipeline = AssessmentPipeline(
                AssessmentRepo(session),
                person_service=PersonService(
                    PersonRepo(session),
                    facility_resolver,
                    PersonDetailBuilder(TubeFeedCalculator(food_repository)),
                ),
                embedding_repository=EmbeddingRepo(session),
                food_repository=food_repository,
            )
            assessments = await pipeline.generate_many(options.persons)
        return Output(
            result=AssessmentGenerationResult.from_assessments(assessments),
            controller=self.name,
            exit_code=0,
        )


__all__ = [
    "AssessmentGenerationController",
    "AssessmentGenerationOptions",
    "AssessmentGenerationResult",
    "GeneratedPersonAssessment",
    "PersonAssessmentGenerationOptions",
]
