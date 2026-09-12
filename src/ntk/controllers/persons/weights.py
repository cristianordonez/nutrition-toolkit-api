"""Return weights for selected persons."""

from __future__ import annotations

import typing

from pydantic import BaseModel, Field

from ntk.controllers.base import BaseController
from ntk.controllers.session import controller_session
from ntk.models.base import ConsoleRenderableModel
from ntk.models.output import Output
from ntk.models.sql.clinical import PersonWeight  # noqa: TC001
from ntk.repositories.person_repo import PersonRepo

if typing.TYPE_CHECKING:
    from sqlmodel import Session


class PersonWeightsOptions(BaseModel):
    """Person IDs whose weights should be returned."""

    person_ids: list[int] = Field(
        min_length=1,
        description="Database IDs of persons",
    )


class PersonWeightsResult(ConsoleRenderableModel):
    """Weights belonging to the requested persons."""

    weights: list[PersonWeight]

    def to_console(self) -> str:
        """Render weights as formatted JSON."""
        return self.model_dump_json(indent=2)


class PersonWeightsController(BaseController):
    """Retrieve weights for one or more persons."""

    name = "weights"
    help = "Get weights by person ID"
    options_model = PersonWeightsOptions

    def __init__(self, session: Session | None = None) -> None:
        """Store the optional controller-owned session."""
        self.session = session

    def run(
        self,
        options: PersonWeightsOptions,
    ) -> Output[PersonWeightsResult]:
        """Return weights for the supplied person IDs."""
        with controller_session(self.session) as session:
            weights = PersonRepo(session).get_weights_by_person_ids(
                options.person_ids,
            )
        return Output(
            result=PersonWeightsResult(weights=weights),
            controller=self.name,
            exit_code=0,
        )


__all__ = [
    "PersonWeightsController",
    "PersonWeightsOptions",
    "PersonWeightsResult",
]
