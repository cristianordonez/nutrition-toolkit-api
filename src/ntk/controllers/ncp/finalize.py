"""CLI command for finalizing one person ncp."""

from __future__ import annotations

import typing

from pydantic import BaseModel

from ntk.controllers.base import BaseController
from ntk.controllers.session import controller_session
from ntk.models.base import ConsoleRenderableModel
from ntk.models.output import Output
from ntk.models.sql.person import PersonClinicalNote  # noqa: TC001
from ntk.pipelines.ncp import NutritionCareProcessPipeline
from ntk.repositories.clinical_note_repo import ClinicalNoteRepo

if typing.TYPE_CHECKING:
    from sqlmodel import Session


class NCPFinalizeOptions(BaseModel):
    """Nutrition Care Process to finalize."""

    ncp_id: int


class NCPFinalizeController(BaseController):
    """Finalize one person ncp."""

    name = "finalize"
    help = "Finalize an ncp by ID"
    options_model = NCPFinalizeOptions

    def __init__(self, session: Session | None = None) -> None:
        """Store the optional controller-owned session."""
        self.session = session

    async def run(
        self,
        options: NCPFinalizeOptions,
    ) -> Output[PersonClinicalNote]:
        """Finalize and return the requested ncp."""
        with controller_session(self.session) as session:
            ncp = await NutritionCareProcessPipeline(
                ClinicalNoteRepo(session),
            ).finalize(options.ncp_id)
            if ncp is None:
                message = f"Nutrition Care Process {options.ncp_id} was not found"
                raise LookupError(message)
        return Output(result=ncp, controller=self.name, exit_code=0)


class NCPFinalizeCommandResult(ConsoleRenderableModel):
    """Finalized ncp returned for display by the CLI."""

    ncp: PersonClinicalNote

    def to_console(self) -> str:
        """Render the finalized ncp as formatted JSON."""
        return self.ncp.model_dump_json(indent=2)


class NCPFinalizeCommandController(BaseController):
    """Finalize one person ncp from the CLI."""

    name = "finalize"
    help = "Finalize an ncp by ID"
    options_model = NCPFinalizeOptions

    def __init__(self, session: Session | None = None) -> None:
        """Store the optional controller-owned session."""
        self.session = session

    async def run(
        self,
        options: NCPFinalizeOptions,
    ) -> Output[NCPFinalizeCommandResult]:
        """Finalize the requested ncp or raise when it does not exist."""
        with controller_session(self.session) as session:
            pipeline = NutritionCareProcessPipeline(ClinicalNoteRepo(session))
            ncp = await pipeline.finalize(options.ncp_id)
            if ncp is None:
                message = f"Nutrition Care Process {options.ncp_id} was not found"
                raise LookupError(message)
        return Output(
            result=NCPFinalizeCommandResult(ncp=ncp),
            controller=self.name,
            exit_code=0,
        )


__all__ = [
    "NCPFinalizeCommandController",
    "NCPFinalizeCommandResult",
    "NCPFinalizeController",
    "NCPFinalizeOptions",
]
