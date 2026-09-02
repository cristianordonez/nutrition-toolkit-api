"""CLI command for retrieving one resident assessment."""

from __future__ import annotations

import typing

from pydantic import BaseModel, Field

from ntk.controllers.base import BaseController
from ntk.controllers.session import controller_session
from ntk.models.base import ConsoleRenderableModel
from ntk.models.output import Output
from ntk.models.sql.resident import ResidentAssessment  # noqa: TC001
from ntk.repositories.assessment_repo import AssessmentRepo

if typing.TYPE_CHECKING:
    from sqlmodel import Session


class AssessmentGetOptions(BaseModel):
    """Identifier of the assessment to retrieve."""

    assessment_id: int = Field(description="Resident assessment ID")


class AssessmentGetCommandResult(ConsoleRenderableModel):
    """Assessment retrieved for display by the CLI."""

    assessment: ResidentAssessment

    def to_console(self) -> str:
        """Render the assessment as formatted JSON."""
        return self.assessment.model_dump_json(indent=2)


class AssessmentGetCommandController(BaseController):
    """Retrieve one assessment by ID for the CLI."""

    name = "get"
    help = "Get an assessment by ID"
    options_model = AssessmentGetOptions

    def __init__(self, session: Session | None = None) -> None:
        """Store the optional controller-owned session."""
        self.session = session

    def run(
        self,
        options: AssessmentGetOptions,
    ) -> Output[AssessmentGetCommandResult]:
        """Return the requested assessment or raise when it does not exist."""
        with controller_session(self.session) as session:
            assessment = AssessmentRepo(session).get_by_id(options.assessment_id)
            if assessment is None:
                message = f"Assessment {options.assessment_id} was not found"
                raise LookupError(message)
        return Output(
            result=AssessmentGetCommandResult(assessment=assessment),
            controller=self.name,
            exit_code=0,
        )


__all__ = [
    "AssessmentGetCommandController",
    "AssessmentGetCommandResult",
    "AssessmentGetOptions",
]
