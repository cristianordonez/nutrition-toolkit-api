"""Return ncps for selected persons."""

from __future__ import annotations

import typing

from pydantic import BaseModel, Field

from ntk.controllers.base import BaseController
from ntk.controllers.session import controller_session
from ntk.models.base import ConsoleRenderableModel
from ntk.models.output import Output
from ntk.models.sql.person import PersonClinicalNote  # noqa: TC001
from ntk.repositories.person_repo import PersonRepo

if typing.TYPE_CHECKING:
    from sqlmodel import Session


class PersonNCPsOptions(BaseModel):
    """Person IDs whose ncps should be returned."""

    person_ids: list[int] = Field(
        min_length=1,
        description="Database IDs of persons",
    )


class PersonNCPsResult(ConsoleRenderableModel):
    """Nutrition Care Processes belonging to the requested persons."""

    ncps: list[PersonClinicalNote]

    def to_console(self) -> str:
        """Render ncps as formatted JSON."""
        return self.model_dump_json(indent=2)


class PersonNCPsController(BaseController):
    """Retrieve ncps for one or more persons."""

    name = "ncps"
    help = "Get ncps by person ID"
    options_model = PersonNCPsOptions

    def __init__(self, session: Session | None = None) -> None:
        """Store the optional controller-owned session."""
        self.session = session

    def run(
        self,
        options: PersonNCPsOptions,
    ) -> Output[PersonNCPsResult]:
        """Return ncps for the supplied person IDs."""
        with controller_session(self.session) as session:
            ncps = PersonRepo(session).get_ncps_by_person_ids(
                options.person_ids,
            )
        return Output(
            result=PersonNCPsResult(ncps=ncps),
            controller=self.name,
            exit_code=0,
        )


__all__ = [
    "PersonNCPsController",
    "PersonNCPsOptions",
    "PersonNCPsResult",
]
