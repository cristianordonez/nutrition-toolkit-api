"""CLI command for finalizing one Nutrition Care Process."""

from __future__ import annotations

import typing

from pydantic import BaseModel

from api.controllers.session import controller_session
from api.models.sql.ncp import NutritionCareProcess  # noqa: TC001
from api.pipelines.ncp import NutritionCareProcessPipeline
from api.repositories.ncp_repo import NCPRepo
from ntk.controllers.base import BaseController
from ntk.models.base import ConsoleRenderableModel
from ntk.models.output import Output

if typing.TYPE_CHECKING:
    from sqlmodel import Session


class NCPFinalizeOptions(BaseModel):
    """Nutrition Care Process to finalize."""

    ncp_id: int
    person_identifier: str


class NCPFinalizeCommandResult(ConsoleRenderableModel):
    """Finalized ncp returned for display by the CLI."""

    ncp: NutritionCareProcess

    def to_console(self) -> str:
        """Render the finalized ncp as formatted JSON."""
        return self.ncp.model_dump_json(indent=2)


class NCPFinalizeCommandController(BaseController):
    """Finalize one Nutrition Care Process from the CLI."""

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
            pipeline = NutritionCareProcessPipeline(NCPRepo(session))
            ncp = await pipeline.finalize(options.ncp_id, options.person_identifier)
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
    "NCPFinalizeOptions",
]
