"""Return a concise data-coverage summary for one person."""

from __future__ import annotations

import typing

from pydantic import BaseModel, Field

from engine.controllers.base import BaseController
from engine.database.sessions import controller_session
from engine.models.output import Output
from engine.repositories.person_repo import PersonRepo
from engine.services.person.person_service import PersonService
from engine.services.person.summary_service import PersonSummaryService

if typing.TYPE_CHECKING:
    from sqlmodel import Session

    from engine.models.person_summary import PersonDataSummary


class PersonSummaryOptions(BaseModel):
    """Person whose local data coverage should be summarized."""

    person_id: int = Field(gt=0, description="Database ID of the person")


class PersonSummaryController(BaseController):
    """Build a UI-facing summary from one person's complete local detail."""

    name = "summary"
    help = "Summarize available and missing person data"
    options_model = PersonSummaryOptions

    def __init__(self, session: Session | None = None) -> None:
        """Store the optional controller-owned session."""
        self.session = session

    def run(
        self,
        options: PersonSummaryOptions,
    ) -> Output[PersonDataSummary]:
        """Return available and missing data for the requested person."""
        with controller_session(self.session) as session:
            detail = PersonService(PersonRepo(session)).get_person_detail_by_id(
                options.person_id,
            )
            summary = PersonSummaryService.build(detail)
        return Output(
            result=summary,
            controller=self.name,
            exit_code=0,
        )


__all__ = ["PersonSummaryController", "PersonSummaryOptions"]
