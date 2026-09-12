"""Return assessments for selected persons."""

from __future__ import annotations

import typing

from pydantic import BaseModel, Field

from ntk.controllers.base import BaseController
from ntk.controllers.session import controller_session
from ntk.models.base import ConsoleRenderableModel
from ntk.models.output import Output
from ntk.models.sql.person import PersonAssessment  # noqa: TC001
from ntk.repositories.person_repo import PersonRepo

if typing.TYPE_CHECKING:
    from sqlmodel import Session


class PersonAssessmentsOptions(BaseModel):
    """Person IDs whose assessments should be returned."""

    person_ids: list[int] = Field(
        min_length=1,
        description="Database IDs of persons",
    )


class PersonAssessmentsResult(ConsoleRenderableModel):
    """Assessments belonging to the requested persons."""

    assessments: list[PersonAssessment]

    def to_console(self) -> str:
        """Render assessments as formatted JSON."""
        return self.model_dump_json(indent=2)


class PersonAssessmentsController(BaseController):
    """Retrieve assessments for one or more persons."""

    name = "assessments"
    help = "Get assessments by person ID"
    options_model = PersonAssessmentsOptions

    def __init__(self, session: Session | None = None) -> None:
        """Store the optional controller-owned session."""
        self.session = session

    def run(
        self,
        options: PersonAssessmentsOptions,
    ) -> Output[PersonAssessmentsResult]:
        """Return assessments for the supplied person IDs."""
        with controller_session(self.session) as session:
            assessments = PersonRepo(session).get_assessments_by_person_ids(
                options.person_ids,
            )
        return Output(
            result=PersonAssessmentsResult(assessments=assessments),
            controller=self.name,
            exit_code=0,
        )


__all__ = [
    "PersonAssessmentsController",
    "PersonAssessmentsOptions",
    "PersonAssessmentsResult",
]
