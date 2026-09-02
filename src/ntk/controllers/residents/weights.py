"""Return weights for selected residents."""

from __future__ import annotations

import typing

from pydantic import BaseModel, Field

from ntk.controllers.base import BaseController
from ntk.controllers.session import controller_session
from ntk.models.base import ConsoleRenderableModel
from ntk.models.output import Output
from ntk.models.sql.clinical import ResidentWeight  # noqa: TC001
from ntk.repositories.resident_repo import ResidentRepo

if typing.TYPE_CHECKING:
    from sqlmodel import Session


class ResidentWeightsOptions(BaseModel):
    """Resident IDs whose weights should be returned."""

    resident_ids: list[int] = Field(
        min_length=1,
        description="Database IDs of residents",
    )


class ResidentWeightsResult(ConsoleRenderableModel):
    """Weights belonging to the requested residents."""

    weights: list[ResidentWeight]

    def to_console(self) -> str:
        """Render weights as formatted JSON."""
        return self.model_dump_json(indent=2)


class ResidentWeightsController(BaseController):
    """Retrieve weights for one or more residents."""

    name = "weights"
    help = "Get weights by resident ID"
    options_model = ResidentWeightsOptions

    def __init__(self, session: Session | None = None) -> None:
        """Store the optional controller-owned session."""
        self.session = session

    def run(
        self,
        options: ResidentWeightsOptions,
    ) -> Output[ResidentWeightsResult]:
        """Return weights for the supplied resident IDs."""
        with controller_session(self.session) as session:
            weights = ResidentRepo(session).get_weights_by_resident_ids(
                options.resident_ids,
            )
        return Output(
            result=ResidentWeightsResult(weights=weights),
            controller=self.name,
            exit_code=0,
        )


__all__ = [
    "ResidentWeightsController",
    "ResidentWeightsOptions",
    "ResidentWeightsResult",
]
