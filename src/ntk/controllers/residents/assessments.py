"""Return assessments for selected residents."""

from __future__ import annotations

import typing

from pydantic import BaseModel, Field

from ntk.controllers.base import BaseController
from ntk.controllers.session import controller_session
from ntk.models.base import ConsoleRenderableModel
from ntk.models.output import Output
from ntk.models.sql.resident import ResidentAssessment  # noqa: TC001
from ntk.repositories.resident_repo import ResidentRepo

if typing.TYPE_CHECKING:
    from sqlmodel import Session


class ResidentAssessmentsOptions(BaseModel):
    """Resident IDs whose assessments should be returned."""

    resident_ids: list[int] = Field(
        min_length=1,
        description="Database IDs of residents",
    )


class ResidentAssessmentsResult(ConsoleRenderableModel):
    """Assessments belonging to the requested residents."""

    assessments: list[ResidentAssessment]

    def to_console(self) -> str:
        """Render assessments as formatted JSON."""
        return self.model_dump_json(indent=2)


class ResidentAssessmentsController(BaseController):
    """Retrieve assessments for one or more residents."""

    name = "assessments"
    help = "Get assessments by resident ID"
    options_model = ResidentAssessmentsOptions

    def __init__(self, session: Session | None = None) -> None:
        """Store the optional controller-owned session."""
        self.session = session

    def run(
        self,
        options: ResidentAssessmentsOptions,
    ) -> Output[ResidentAssessmentsResult]:
        """Return assessments for the supplied resident IDs."""
        with controller_session(self.session) as session:
            assessments = ResidentRepo(session).get_assessments_by_resident_ids(
                options.resident_ids,
            )
        return Output(
            result=ResidentAssessmentsResult(assessments=assessments),
            controller=self.name,
            exit_code=0,
        )


__all__ = [
    "ResidentAssessmentsController",
    "ResidentAssessmentsOptions",
    "ResidentAssessmentsResult",
]
