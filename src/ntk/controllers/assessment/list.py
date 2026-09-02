"""List persisted resident assessments."""

from __future__ import annotations

import typing

from pydantic import BaseModel

from ntk.controllers.base import BaseController
from ntk.controllers.session import controller_session
from ntk.models.output import Output
from ntk.models.sql.resident import ResidentAssessment  # noqa: TC001
from ntk.repositories.assessment_repo import AssessmentRepo

if typing.TYPE_CHECKING:
    from sqlmodel import Session


class AssessmentListOptions(BaseModel):
    """Options for listing assessments."""


class AssessmentListResult(BaseModel):
    """Persisted resident assessments."""

    assessments: list[ResidentAssessment]


class AssessmentListController(BaseController):
    """Return all persisted resident assessments."""

    name = "list"
    help = "List assessments"
    options_model = AssessmentListOptions

    def __init__(self, session: Session | None = None) -> None:
        """Store the optional controller-owned session."""
        self.session = session

    def run(
        self,
        options: AssessmentListOptions,
    ) -> Output[AssessmentListResult]:
        """Return all assessments newest first."""
        del options
        with controller_session(self.session) as session:
            assessments = AssessmentRepo(session).get_all()
        return Output(
            result=AssessmentListResult(assessments=assessments),
            controller=self.name,
            exit_code=0,
        )


__all__ = [
    "AssessmentListController",
    "AssessmentListOptions",
    "AssessmentListResult",
]
