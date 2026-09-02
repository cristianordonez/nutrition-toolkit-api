"""Update one persisted resident assessment."""

from __future__ import annotations

import typing
from datetime import date  # noqa: TC003 - Pydantic resolves date at runtime

from pydantic import BaseModel

from ntk.controllers.base import BaseController
from ntk.controllers.session import controller_session
from ntk.models.output import Output
from ntk.models.sql.resident import ResidentAssessment, StatusType  # noqa: TC001
from ntk.repositories.assessment_repo import AssessmentRepo
from ntk.services.assessment.update_service import AssessmentUpdateService

if typing.TYPE_CHECKING:
    from sqlmodel import Session


class AssessmentUpdateRequest(BaseModel):
    """Editable resident assessment fields."""

    content: str | None = None
    assessment_date: date | None = None
    created_by: str | None = None
    status: StatusType | None = None


class AssessmentUpdateOptions(AssessmentUpdateRequest):
    """Assessment identifier and editable fields."""

    assessment_id: int


class AssessmentUpdateController(BaseController):
    """Update one resident assessment."""

    name = "update"
    help = "Update an assessment"
    options_model = AssessmentUpdateOptions

    def __init__(self, session: Session | None = None) -> None:
        """Store the optional controller-owned session."""
        self.session = session

    async def run(
        self,
        options: AssessmentUpdateOptions,
    ) -> Output[ResidentAssessment]:
        """Update the requested assessment or raise when it does not exist."""
        with controller_session(self.session) as session:
            assessment = await AssessmentUpdateService(
                AssessmentRepo(session),
            ).update(
                options.assessment_id,
                content=options.content,
                assessment_date=options.assessment_date,
                created_by=options.created_by,
                status=options.status,
            )
            if assessment is None:
                message = f"Assessment {options.assessment_id} was not found"
                raise LookupError(message)
        return Output(result=assessment, controller=self.name, exit_code=0)


__all__ = [
    "AssessmentUpdateController",
    "AssessmentUpdateOptions",
    "AssessmentUpdateRequest",
]
