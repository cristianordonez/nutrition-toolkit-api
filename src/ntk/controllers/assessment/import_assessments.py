"""Import assessments from a progress-note report."""

from __future__ import annotations

import pathlib  # noqa: TC003 - Pydantic resolves Path at runtime
import typing

from pydantic import BaseModel, Field

from ntk.controllers.base import BaseController
from ntk.controllers.session import controller_session
from ntk.controllers.uploads import (
    ReadableUpload,
    UploadRequirements,
    materialize_uploads,
)
from ntk.models.base import ConsoleRenderableModel
from ntk.models.output import Output
from ntk.models.sql.resident import ResidentAssessment  # noqa: TC001 - Pydantic runtime
from ntk.repositories.assessment_repo import AssessmentRepo
from ntk.repositories.facility_repo import FacilityRepo
from ntk.repositories.progress_note_repo import ProgressNoteRepo
from ntk.repositories.resident_facility_stay_repo import ResidentFacilityStayRepo
from ntk.repositories.resident_repo import ResidentRepo
from ntk.services.assessment import AssessmentSyncService
from ntk.services.resident_data import ResidentIngestionService
from ntk.services.resident_data.resident_resolver import ResidentResolver

if typing.TYPE_CHECKING:
    from sqlmodel import Session


class AssessmentImportOptions(BaseModel):
    """Progress-note report containing nutrition assessments."""

    path: pathlib.Path = Field(description="PCC progress-note report PDF")
    overwrite: bool = False
    created_by: str | None = None


class AssessmentImportResult(ConsoleRenderableModel):
    """Nutrition assessments imported from one progress-note report."""

    assessments: list[ResidentAssessment]

    def to_console(self) -> str:
        """Render the IDs of imported assessments."""
        return "\n".join(str(assessment.id) for assessment in self.assessments)


class AssessmentImportController(BaseController):
    """Import nutrition notes as finalized resident assessments."""

    name = "import"
    help = "Import nutrition assessments from a PCC progress-note report"
    options_model = AssessmentImportOptions

    def __init__(self, session: Session | None = None) -> None:
        """Store the optional controller-owned session."""
        self.session = session

    async def run_upload(
        self,
        file: ReadableUpload,
        *,
        overwrite: bool = False,
        created_by: str | None = None,
    ) -> Output[AssessmentImportResult]:
        """Materialize and import one uploaded progress-note report."""
        async with materialize_uploads(
            [file],
            UploadRequirements(
                allowed_suffixes=frozenset({".pdf"}),
                file_description="PCC progress-note report PDF",
                directory_prefix="ntk-assessment-import-",
                default_filename=lambda _index: "progress-notes.pdf",
            ),
        ) as uploads:
            return await self.run(
                AssessmentImportOptions(
                    path=uploads.paths[0],
                    overwrite=overwrite,
                    created_by=created_by,
                ),
            )

    async def run(
        self,
        options: AssessmentImportOptions,
    ) -> Output[AssessmentImportResult]:
        """Ingest progress notes, then synchronize historical assessments."""
        if not options.path.is_file():
            message = f"Progress-note report does not exist: {options.path}"
            raise ValueError(message)
        if options.path.suffix.casefold() != ".pdf":
            message = f"Progress-note report is not a PDF: {options.path}"
            raise ValueError(message)
        with controller_session(self.session) as session:
            resident_resolver = ResidentResolver(
                resident_repository=ResidentRepo(session),
                facility_repository=FacilityRepo(session),
                stay_repository=ResidentFacilityStayRepo(session),
            )
            progress_note_repository = ProgressNoteRepo(session)
            ingestion_service = ResidentIngestionService(
                progress_note_repository=progress_note_repository,
                resident_resolver=resident_resolver,
            )
            await ingestion_service.ingest([options.path])
            sync_result = await AssessmentSyncService(
                progress_note_repository,
                AssessmentRepo(session),
            ).sync_assessments()
        return Output(
            result=AssessmentImportResult(
                assessments=sync_result.created_assessments,
            ),
            controller=self.name,
            exit_code=0,
        )


__all__ = [
    "AssessmentImportController",
    "AssessmentImportOptions",
    "AssessmentImportResult",
]
