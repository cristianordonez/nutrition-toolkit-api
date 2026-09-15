"""Synchronize historical ncps from persisted clinical notes."""

from __future__ import annotations

import typing

from pydantic import BaseModel

from api.controllers.session import controller_session
from api.pipelines.ncp import NutritionCareProcessPipeline
from api.repositories.ncp_repo import NCPRepo
from ntk.controllers.base import BaseController
from ntk.models.output import Output

if typing.TYPE_CHECKING:
    from sqlmodel import Session


class NCPSyncOptions(BaseModel):
    """Options for synchronizing all persisted clinical notes."""


class NCPSyncController(BaseController):
    """Run historical ncp synchronization without document extraction.

    Deferred: raises ``NotImplementedError`` (see the split refactor plan,
    decision 7) -- this promotion has no coherent home now that NCP
    generation/storage lives behind cloud-api's stateless HTTP boundary.
    """

    name = "sync"
    help = "Synchronize Nutrition Care Processes from persisted clinical notes"
    options_model = NCPSyncOptions

    def __init__(self, session: Session | None = None) -> None:
        """Store the optional controller-owned session."""
        self.session = session

    async def run(
        self,
        options: NCPSyncOptions,
    ) -> Output[typing.Any]:
        """Synchronize ncps and embeddings using one database session."""
        del options
        with controller_session(self.session) as session:
            result = await NutritionCareProcessPipeline(
                NCPRepo(session),
            ).sync_ncps()
        return Output(result=result, controller=self.name, exit_code=0)


__all__ = ["NCPSyncController", "NCPSyncOptions"]
