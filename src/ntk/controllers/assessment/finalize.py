"""CLI command for finalizing one person assessment."""

from __future__ import annotations

import typing

from pydantic import BaseModel

from ntk.controllers.base import BaseController
from ntk.controllers.session import controller_session
from ntk.models.base import ConsoleRenderableModel
from ntk.models.output import Output
from ntk.models.sql.person import PersonAssessment  # noqa: TC001
from ntk.pipelines.assessment import AssessmentPipeline
from ntk.repositories.assessment_repo import AssessmentRepo

if typing.TYPE_CHECKING:
    from sqlmodel import Session


class AssessmentFinalizeOptions(BaseModel):
    """Assessment to finalize."""

    assessment_id: int


class AssessmentFinalizeController(BaseController):
    """Finalize one person assessment."""

    name = "finalize"
    help = "Finalize an assessment by ID"
    options_model = AssessmentFinalizeOptions

    def __init__(self, session: Session | None = None) -> None:
        """Store the optional controller-owned session."""
        self.session = session

    async def run(
        self,
        options: AssessmentFinalizeOptions,
    ) -> Output[PersonAssessment]:
        """Finalize and return the requested assessment."""
        with controller_session(self.session) as session:
            assessment = await AssessmentPipeline(
                AssessmentRepo(session),
            ).finalize(options.assessment_id)
            if assessment is None:
                message = f"Assessment {options.assessment_id} was not found"
                raise LookupError(message)
        return Output(result=assessment, controller=self.name, exit_code=0)


class AssessmentFinalizeCommandResult(ConsoleRenderableModel):
    """Finalized assessment returned for display by the CLI."""

    assessment: PersonAssessment

    def to_console(self) -> str:
        """Render the finalized assessment as formatted JSON."""
        return self.assessment.model_dump_json(indent=2)


class AssessmentFinalizeCommandController(BaseController):
    """Finalize one person assessment from the CLI."""

    name = "finalize"
    help = "Finalize an assessment by ID"
    options_model = AssessmentFinalizeOptions

    def __init__(self, session: Session | None = None) -> None:
        """Store the optional controller-owned session."""
        self.session = session

    async def run(
        self,
        options: AssessmentFinalizeOptions,
    ) -> Output[AssessmentFinalizeCommandResult]:
        """Finalize the requested assessment or raise when it does not exist."""
        with controller_session(self.session) as session:
            pipeline = AssessmentPipeline(AssessmentRepo(session))
            assessment = await pipeline.finalize(options.assessment_id)
            if assessment is None:
                message = f"Assessment {options.assessment_id} was not found"
                raise LookupError(message)
        return Output(
            result=AssessmentFinalizeCommandResult(assessment=assessment),
            controller=self.name,
            exit_code=0,
        )


__all__ = [
    "AssessmentFinalizeCommandController",
    "AssessmentFinalizeCommandResult",
    "AssessmentFinalizeController",
    "AssessmentFinalizeOptions",
]
