"""Synchronize historical assessments from persisted progress notes."""

from __future__ import annotations

import typing

from pydantic import BaseModel

from ntk.controllers.base import BaseController
from ntk.controllers.session import controller_session
from ntk.models.output import Output
from ntk.repositories.assessment_repo import AssessmentRepo
from ntk.repositories.progress_note_repo import ProgressNoteRepo
from ntk.services.assessment import AssessmentSyncResult, AssessmentSyncService

if typing.TYPE_CHECKING:
    from sqlmodel import Session


class AssessmentSyncOptions(BaseModel):
    """Options for synchronizing all persisted progress notes."""


class AssessmentSyncController(BaseController):
    """Run historical assessment synchronization without document extraction."""

    name = "sync"
    help = "Synchronize nutrition assessments from persisted progress notes"
    options_model = AssessmentSyncOptions

    def __init__(self, session: Session | None = None) -> None:
        """Store the optional controller-owned session."""
        self.session = session

    async def run(
        self,
        options: AssessmentSyncOptions,
    ) -> Output[AssessmentSyncResult]:
        """Synchronize assessments and embeddings using one database session."""
        del options
        with controller_session(self.session) as session:
            result = await AssessmentSyncService(
                ProgressNoteRepo(session),
                AssessmentRepo(session),
            ).sync_assessments()
        return Output(result=result, controller=self.name, exit_code=0)


__all__ = ["AssessmentSyncController", "AssessmentSyncOptions"]
