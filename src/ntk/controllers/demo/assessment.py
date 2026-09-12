"""Generate one assessment from multiple uploaded clinical documents."""

from __future__ import annotations

import typing

from pydantic import BaseModel, Field

from ntk.controllers.base import BaseController
from ntk.controllers.session import controller_session
from ntk.models.output import Output
from ntk.pipelines.demo import DemoAssessmentPipeline
from ntk.repositories.embedding_repo import EmbeddingRepo
from ntk.repositories.food_repo import FoodRepo
from ntk.services.calculators.tubefeed_calculator import TubeFeedCalculator
from ntk.services.embedding_service import EmbeddingService
from ntk.services.person.detail_builder import PersonDetailBuilder

if typing.TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlmodel import Session

    from ntk.controllers.uploads import ReadableUpload
    from ntk.models.demo_assessment import DemoAssessmentResponse


class DemoAssessmentOptions(BaseModel):
    """Clinical documents to combine into one demo assessment."""

    files: list[typing.Any] = Field(min_length=1)


class DemoAssessmentController(BaseController):
    """Coordinate the request-scoped demo assessment workflow."""

    name = "demo-assessment"
    help = "Generate one demo assessment from clinical documents"
    options_model = DemoAssessmentOptions

    def __init__(self, session: Session | None = None) -> None:
        """Store an injected session or create one for this controller run."""
        self.session = session

    async def run(
        self,
        options: DemoAssessmentOptions,
    ) -> Output[DemoAssessmentResponse]:
        """Extract all uploads and generate one unsaved combined assessment."""
        with controller_session(self.session) as session:
            food_repository = FoodRepo(session)
            embedding_service = EmbeddingService(EmbeddingRepo(session))
            result = await DemoAssessmentPipeline(
                food_repository,
                embedding_service,
                detail_builder=PersonDetailBuilder(
                    TubeFeedCalculator(food_repository),
                ),
            ).run_uploads(
                typing.cast("Sequence[ReadableUpload]", options.files),
            )
        return Output(result=result, controller=self.name, exit_code=0)


__all__ = ["DemoAssessmentController", "DemoAssessmentOptions"]
