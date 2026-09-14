"""Update one persisted person ncp."""

from __future__ import annotations

import typing
from datetime import datetime  # noqa: TC003 - Pydantic resolves at runtime

from pydantic import BaseModel

from ntk.controllers.base import BaseController
from ntk.controllers.session import controller_session
from ntk.models.output import Output
from ntk.models.sql.person import (  # noqa: TC001
    NutritionCareProcessStatus,
    PersonClinicalNote,
)
from ntk.pipelines.ncp import NutritionCareProcessPipeline
from ntk.repositories.clinical_note_repo import ClinicalNoteRepo

if typing.TYPE_CHECKING:
    from sqlmodel import Session


class NCPUpdateRequest(BaseModel):
    """Editable person ncp fields."""

    note_text: str | None = None
    note_date: datetime | None = None
    created_by: str | None = None
    status: NutritionCareProcessStatus | None = None


class NCPUpdateOptions(NCPUpdateRequest):
    """Nutrition Care Process identifier and editable fields."""

    ncp_id: int


class NCPUpdateController(BaseController):
    """Update one person ncp."""

    name = "update"
    help = "Update an ncp"
    options_model = NCPUpdateOptions

    def __init__(self, session: Session | None = None) -> None:
        """Store the optional controller-owned session."""
        self.session = session

    async def run(
        self,
        options: NCPUpdateOptions,
    ) -> Output[PersonClinicalNote]:
        """Update the requested ncp or raise when it does not exist."""
        with controller_session(self.session) as session:
            ncp = await NutritionCareProcessPipeline(
                ClinicalNoteRepo(session),
            ).update(
                options.ncp_id,
                note_text=options.note_text,
                note_date=options.note_date,
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
