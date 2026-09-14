"""CLI command for retrieving one person ncp."""

from __future__ import annotations

import typing

from pydantic import BaseModel, Field

from ntk.controllers.base import BaseController
from ntk.controllers.session import controller_session
from ntk.models.base import ConsoleRenderableModel
from ntk.models.output import Output
from ntk.models.sql.person import PersonClinicalNote  # noqa: TC001
from ntk.repositories.clinical_note_repo import ClinicalNoteRepo
from ntk.services.ncp_service import NutritionCareProcessService

if typing.TYPE_CHECKING:
    from sqlmodel import Session


class NCPGetOptions(BaseModel):
    """Identifier of the ncp to retrieve."""

    ncp_id: int = Field(description="Person ncp ID")


class NCPGetCommandResult(ConsoleRenderableModel):
    """Nutrition Care Process retrieved for display by the CLI."""

    ncp: PersonClinicalNote

    def to_console(self) -> str:
        """Render the ncp as formatted JSON."""
        return self.ncp.model_dump_json(indent=2)


class NCPGetCommandController(BaseController):
    """Retrieve one ncp by ID for the CLI."""

    name = "get"
    help = "Get an ncp by ID"
    options_model = NCPGetOptions

    def __init__(self, session: Session | None = None) -> None:
        """Store the optional controller-owned session."""
        self.session = session

    def run(
        self,
        options: NCPGetOptions,
    ) -> Output[NCPGetCommandResult]:
        """Return the requested ncp or raise when it does not exist."""
        with controller_session(self.session) as session:
            ncp = NutritionCareProcessService(ClinicalNoteRepo(session)).get(
                options.ncp_id,
            )
            if ncp is None:
                message = f"Nutrition Care Process {options.ncp_id} was not found"
                raise LookupError(message)
        return Output(
            result=NCPGetCommandResult(ncp=ncp),
            controller=self.name,
            exit_code=0,
        )


__all__ = [
    "NCPGetCommandController",
    "NCPGetCommandResult",
    "NCPGetOptions",
]
