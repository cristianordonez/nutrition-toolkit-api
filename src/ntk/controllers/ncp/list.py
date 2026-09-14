"""List persisted Nutrition Care Processes."""

from __future__ import annotations

import typing

from pydantic import BaseModel

from ntk.controllers.base import BaseController
from ntk.controllers.session import controller_session
from ntk.models.output import Output
from ntk.models.sql.person import PersonClinicalNote  # noqa: TC001
from ntk.repositories.clinical_note_repo import ClinicalNoteRepo
from ntk.services.ncp_service import NutritionCareProcessService

if typing.TYPE_CHECKING:
    from sqlmodel import Session


class NCPListOptions(BaseModel):
    """Options for listing ncps."""


class NCPListResult(BaseModel):
    """Persisted Nutrition Care Processes."""

    ncps: list[PersonClinicalNote]


class NCPListController(BaseController):
    """Return all persisted Nutrition Care Processes."""

    name = "list"
    help = "List ncps"
    options_model = NCPListOptions

    def __init__(self, session: Session | None = None) -> None:
        """Store the optional controller-owned session."""
        self.session = session

    def run(
        self,
        options: NCPListOptions,
    ) -> Output[NCPListResult]:
        """Return all ncps newest first."""
        del options
        with controller_session(self.session) as session:
            ncps = NutritionCareProcessService(
                ClinicalNoteRepo(session),
            ).list_ncps()
        return Output(
            result=NCPListResult(ncps=ncps),
            controller=self.name,
            exit_code=0,
        )


__all__ = [
    "NCPListController",
    "NCPListOptions",
    "NCPListResult",
]
