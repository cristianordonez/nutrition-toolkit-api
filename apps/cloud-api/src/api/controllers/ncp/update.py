"""Update one persisted Nutrition Care Process."""

from __future__ import annotations

import typing

from pydantic import BaseModel

from api.controllers.session import controller_session
from api.models.sql.ncp import (  # noqa: TC001
    NutritionCareProcess,
    NutritionCareProcessStatus,
)
from api.pipelines.ncp import NutritionCareProcessPipeline
from api.repositories.ncp_repo import NCPRepo
from ntk.controllers.base import BaseController
from ntk.models.output import Output

if typing.TYPE_CHECKING:
    from sqlmodel import Session


class NCPUpdateRequest(BaseModel):
    """Editable Nutrition Care Process fields."""

    note_text: str | None = None
    created_by: str | None = None
    status: NutritionCareProcessStatus | None = None


class NCPUpdateOptions(NCPUpdateRequest):
    """Nutrition Care Process identifier and editable fields."""

    ncp_id: int
    person_identifier: str


class NCPUpdateController(BaseController):
    """Update one Nutrition Care Process."""

    name = "update"
    help = "Update an ncp"
    options_model = NCPUpdateOptions

    def __init__(self, session: Session | None = None) -> None:
        """Store the optional controller-owned session."""
        self.session = session

    async def run(
        self,
        options: NCPUpdateOptions,
    ) -> Output[NutritionCareProcess]:
        """Update the requested ncp or raise when it does not exist."""
        with controller_session(self.session) as session:
            ncp = await NutritionCareProcessPipeline(
                NCPRepo(session),
            ).update(
                options.ncp_id,
                options.person_identifier,
                note_text=options.note_text,
                created_by=options.created_by,
                status=options.status,
            )
            if ncp is None:
                message = f"Nutrition Care Process {options.ncp_id} was not found"
                raise LookupError(message)
        return Output(result=ncp, controller=self.name, exit_code=0)


__all__ = [
    "NCPUpdateController",
    "NCPUpdateOptions",
    "NCPUpdateRequest",
]
