"""Workflow for importing nutrition assessments from progress-note reports."""

from __future__ import annotations

import pathlib
import typing
from tempfile import TemporaryDirectory

from ntk.pipelines.assessment.create.pipeline import AssessmentPipeline
from ntk.pipelines.person.ingestion.extract.pcc_progress_notes import (
    PccProgressNotesExtractor,
)
from ntk.pipelines.person.ingestion.pipeline import PersonIngestionPipeline
from ntk.repositories.assessment_repo import AssessmentRepo
from ntk.repositories.facility_repo import FacilityRepo
from ntk.repositories.person_repo import PersonRepo
from ntk.repositories.progress_note_repo import ProgressNoteRepo
from ntk.services.facility_resolver import FacilityResolver
from ntk.services.person.person_service import PersonService

if typing.TYPE_CHECKING:
    from sqlmodel import Session

    from ntk.models.sql.person import PersonAssessment


class ReadableAssessmentUpload(typing.Protocol):
    """Minimal uploaded-file interface required by assessment import."""

    filename: str | None

    async def read(self) -> bytes:
        """Return the uploaded file contents."""
        ...


class InvalidProgressNoteReportError(ValueError):
    """Raised when an assessment-import file is not a PCC progress-note report."""


class AssessmentImportPipeline:
    """Ingest progress notes and synchronize their nutrition assessments."""

    def __init__(
        self,
        ingestion_service: PersonIngestionPipeline,
        assessment_pipeline: AssessmentPipeline,
    ) -> None:
        """Store the two workflows that comprise assessment import."""
        self.ingestion_service = ingestion_service
        self.assessment_pipeline = assessment_pipeline

    @classmethod
    def from_session(cls, session: Session) -> AssessmentImportPipeline:
        """Build the import workflow from one request or CLI database session."""
        facility_resolver = FacilityResolver(FacilityRepo(session))
        person_service = PersonService(
            PersonRepo(session),
            facility_resolver,
        )
        progress_note_repository = ProgressNoteRepo(session)
        return cls(
            PersonIngestionPipeline(
                progress_note_repository=progress_note_repository,
                person_service=person_service,
                facility_resolver=facility_resolver,
            ),
            AssessmentPipeline(
                AssessmentRepo(session),
                progress_note_repository=progress_note_repository,
            ),
        )

    async def run_upload(
        self,
        file: ReadableAssessmentUpload,
        *,
        overwrite: bool = False,
        created_by: str | None = None,
    ) -> list[PersonAssessment]:
        """Materialize and import one uploaded PDF report."""
        del overwrite, created_by
        filename = pathlib.Path(file.filename or "progress-notes.pdf").name
        if pathlib.Path(filename).suffix.casefold() != ".pdf":
            message = f"'{filename}' is not a PCC progress-note report PDF"
            raise InvalidProgressNoteReportError(message)
        with TemporaryDirectory(prefix="ntk-assessment-import-") as directory:
            path = pathlib.Path(directory) / filename
            path.write_bytes(await file.read())
            return await self.run(path)

    async def run(self, path: pathlib.Path) -> list[PersonAssessment]:
        """Ingest one progress-note PDF and return newly synchronized assessments."""
        self._validate_report_path(path)
        self._validate_progress_note_report(path)
        await self.ingestion_service.ingest([path])
        sync_result = await self.assessment_pipeline.sync_assessments()
        return sync_result.created_assessments

    @staticmethod
    def _validate_report_path(path: pathlib.Path) -> None:
        """Require an existing PDF progress-note report."""
        if not path.is_file():
            message = f"Progress-note report does not exist: {path}"
            raise ValueError(message)
        if path.suffix.casefold() != ".pdf":
            message = f"Progress-note report is not a PDF: {path}"
            raise InvalidProgressNoteReportError(message)

    @staticmethod
    def _validate_progress_note_report(path: pathlib.Path) -> None:
        """Require the PDF to match the PCC progress-note report format."""
        try:
            is_progress_note_report = PccProgressNotesExtractor(
                path,
            ).is_expected_format()
        except RuntimeError as error:
            message = f"'{path.name}' is not a readable PCC progress-note report"
            raise InvalidProgressNoteReportError(message) from error
        if not is_progress_note_report:
            message = f"'{path.name}' is not a PCC progress-note report"
            raise InvalidProgressNoteReportError(message)


__all__ = [
    "AssessmentImportPipeline",
    "InvalidProgressNoteReportError",
    "ReadableAssessmentUpload",
]
