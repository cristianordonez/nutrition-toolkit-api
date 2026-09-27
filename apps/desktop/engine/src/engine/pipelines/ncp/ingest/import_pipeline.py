"""Workflow for importing clinical-note reports as clinical source material.

Imported progress notes retain their provenance in ``clinical_source`` and
may yield structured clinical facts. They are deliberately not copied into
``ncp_note``: that table contains generated NCP lifecycle records and curated
style examples, not every nutrition-related progress note in a source report.
"""

from __future__ import annotations

import pathlib
import typing
from tempfile import TemporaryDirectory

from engine.pipelines.person.ingestion.extract.pcc_progress_notes import (
    PccProgressNotesExtractor,
)
from engine.pipelines.person.ingestion.pipeline import PersonIngestionPipeline
from engine.repositories.clinical_source_repo import ClinicalSourceRepo
from engine.repositories.person_repo import PersonRepo
from engine.services.person.person_service import PersonService

if typing.TYPE_CHECKING:
    from sqlmodel import Session

    from engine.controllers.uploads import ReadableUpload
    from engine.pipelines.person.ingestion.transformer import (
        PersonTransformationResult,
    )


class InvalidClinicalNoteReportError(ValueError):
    """Raised when an ncp-import file is not a PCC clinical-note report."""


class NCPImportPipeline:
    """Ingest clinical notes from a PCC clinical-note report."""

    def __init__(self, ingestion_service: PersonIngestionPipeline) -> None:
        """Store the local ingestion workflow used to persist notes."""
        self.ingestion_service = ingestion_service

    @classmethod
    def from_session(cls, session: Session) -> NCPImportPipeline:
        """Build the import workflow from one request or CLI database session."""
        person_service = PersonService(PersonRepo(session))
        clinical_source_repository = ClinicalSourceRepo(session)
        return cls(
            PersonIngestionPipeline(
                clinical_source_repository=clinical_source_repository,
                person_service=person_service,
            ),
        )

    async def run_upload(
        self,
        file: ReadableUpload,
        *,
        overwrite: bool = False,
        created_by: str | None = None,
    ) -> PersonTransformationResult:
        """Materialize and import one uploaded PDF report."""
        del overwrite, created_by
        filename = pathlib.Path(file.filename or "clinical-notes.pdf").name
        if pathlib.Path(filename).suffix.casefold() != ".pdf":
            message = f"'{filename}' is not a PCC clinical-note report PDF"
            raise InvalidClinicalNoteReportError(message)
        with TemporaryDirectory(prefix="ntk-ncp-import-") as directory:
            path = pathlib.Path(directory) / filename
            path.write_bytes(await file.read())
            return await self.run(path)

    async def run(self, path: pathlib.Path) -> PersonTransformationResult:
        """Ingest one clinical-note PDF report and persist its clinical notes."""
        self._validate_report_path(path)
        self._validate_clinical_note_report(path)
        return await self.ingestion_service.ingest([path])

    @staticmethod
    def _validate_report_path(path: pathlib.Path) -> None:
        """Require an existing PDF clinical-note report."""
        if not path.is_file():
            message = f"Clinical-note report does not exist: {path}"
            raise ValueError(message)
        if path.suffix.casefold() != ".pdf":
            message = f"Clinical-note report is not a PDF: {path}"
            raise InvalidClinicalNoteReportError(message)

    @staticmethod
    def _validate_clinical_note_report(path: pathlib.Path) -> None:
        """Require the PDF to match the PCC clinical-note report format."""
        try:
            is_clinical_note_report = PccProgressNotesExtractor(
                path,
            ).is_expected_format()
        except RuntimeError as error:
            message = f"'{path.name}' is not a readable PCC clinical-note report"
            raise InvalidClinicalNoteReportError(message) from error
        if not is_clinical_note_report:
            message = f"'{path.name}' is not a PCC clinical-note report"
            raise InvalidClinicalNoteReportError(message)


__all__ = [
    "InvalidClinicalNoteReportError",
    "NCPImportPipeline",
]
