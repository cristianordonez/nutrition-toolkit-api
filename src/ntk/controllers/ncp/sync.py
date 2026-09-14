"""Synchronize historical ncps from persisted clinical notes."""

from __future__ import annotations

import typing

from pydantic import BaseModel

from ntk.controllers.base import BaseController
from ntk.controllers.session import controller_session
from ntk.models.output import Output
from ntk.pipelines.ncp import NCPSyncResult, NutritionCareProcessPipeline
from ntk.repositories.clinical_note_repo import ClinicalNoteRepo

if typing.TYPE_CHECKING:
    from sqlmodel import Session


class NCPSyncOptions(BaseModel):
    """Options for synchronizing all persisted clinical notes."""


class NCPSyncController(BaseController):
    """Run historical ncp synchronization without document extraction."""

    name = "sync"
    help = "Synchronize Nutrition Care Processes from persisted clinical notes"
    options_model = NCPSyncOptions

    def __init__(self, session: Session | None = None) -> None:
        """Store the optional controller-owned session."""
        self.session = session

    async def run(
        self,
        options: NCPSyncOptions,
    ) -> Output[NCPSyncResult]:
        """Synchronize ncps and embeddings using one database session."""
        del options
        with controller_session(self.session) as session:
            result = await NutritionCareProcessPipeline(
                ClinicalNoteRepo(session),
            ).sync_ncps()
        return Output(result=result, controller=self.name, exit_code=0)


__all__ = ["NCPSyncController", "NCPSyncOptions"]
