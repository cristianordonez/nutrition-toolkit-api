"""Generate ncps for persisted persons."""

from __future__ import annotations

import typing
from datetime import datetime  # noqa: TC003 - Pydantic resolves at runtime

from pydantic import AliasChoices, BaseModel, Field

from ntk.controllers.base import BaseController
from ntk.controllers.session import controller_session
from ntk.models.output import Output
from ntk.models.sql.person import (
    NutritionCareProcessSource,  # noqa: TC001 - Pydantic resolves this type at runtime
    NutritionCareProcessStatus,  # noqa: TC001 - Pydantic resolves this type at runtime
    PersonClinicalNote,  # noqa: TC001 - used to build the response at runtime
)
from ntk.pipelines.ncp import NutritionCareProcessPipeline
from ntk.repositories.clinical_note_repo import ClinicalNoteRepo
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


class PersonNCPGenerationOptions(BaseModel):
    """One person and their optional ncp guidance."""

    source_person_identifier: str = Field(min_length=1)
    source_system: str = Field(default="pointclickcare", min_length=1)
    facility_identifier: str | None = Field(
        default=None,
        min_length=1,
        validation_alias=AliasChoices("facility_identifier", "facility_id"),
    )
    context: str | None = None


class NCPGenerationOptions(BaseModel):
    """Person-specific ncp generation requests."""

    persons: list[PersonNCPGenerationOptions] = Field(min_length=1)


class GeneratedNCP(BaseModel):
    """Generated ncp enriched with its person's display name."""

    id: int | None
    person_id: int
    person_name: str
    note_date: datetime
    note_type: str | None
    author: str | None
    note_text: str
    ncp_source: NutritionCareProcessSource
    source_filename: str | None
    content_hash: str
    ncp_index: int
    created_by: str
    status: NutritionCareProcessStatus
    model_name: str | None
    created_at: datetime
    finalized_at: datetime | None

    @classmethod
    def from_ncp(
        cls,
        ncp: PersonClinicalNote,
    ) -> GeneratedNCP:
        """Build an API result from an ncp with its person loaded."""
        return cls(
            **ncp.model_dump(),
            person_name=ncp.person.name,
        )


class NCPGenerationResult(BaseModel):
    """Nutrition Care Processes created by one generation request."""

    ncps: list[GeneratedNCP]

    @classmethod
    def from_ncps(
        cls,
        ncps: typing.Iterable[PersonClinicalNote],
    ) -> NCPGenerationResult:
        """Build the shared HTTP/CLI projection for generated ncps."""
        return cls(
            ncps=[GeneratedNCP.from_ncp(ncp) for ncp in ncps],
        )


class NCPGenerationController(BaseController):
    """Generate and persist ncps for requested persons."""

    name = "generate"
    help = "Generate Nutrition Care Processes"
    options_model = NCPGenerationOptions

    def __init__(self, session: Session | None = None) -> None:
        """Store the optional controller-owned session."""
        self.session = session

    async def run(
        self,
        options: NCPGenerationOptions,
    ) -> Output[NCPGenerationResult]:
        """Generate ncps in request order using one session."""
        with controller_session(self.session) as session:
            facility_resolver = FacilityResolver(FacilityRepo(session))
            food_repository = FoodRepo(session)
            pipeline = NutritionCareProcessPipeline(
                ClinicalNoteRepo(session),
                person_service=PersonService(
                    PersonRepo(session),
                    facility_resolver,
                    PersonDetailBuilder(TubeFeedCalculator(food_repository)),
                ),
                embedding_repository=EmbeddingRepo(session),
                food_repository=food_repository,
            )
            ncps = await pipeline.generate_many(options.persons)
        return Output(
            result=NCPGenerationResult.from_ncps(ncps),
            controller=self.name,
            exit_code=0,
        )


__all__ = [
    "GeneratedNCP",
    "NCPGenerationController",
    "NCPGenerationOptions",
    "NCPGenerationResult",
    "PersonNCPGenerationOptions",
]
