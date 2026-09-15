"""Workflow for importing clinical-note reports.

Historically this pipeline also promoted matching notes into searchable
cloud NCPs (``NutritionCareProcessPipeline.sync_ncps()``). That promotion is
deferred (see the split refactor plan, decision 7): NCP generation/storage
now lives behind cloud-api's stateless HTTP boundary, and there is no
device<->cloud sync design yet for imported notes. Local ingestion still
works; only the promotion step is unimplemented.
"""

from __future__ import annotations

import pathlib
import typing
from tempfile import TemporaryDirectory

from engine.pipelines.person.ingestion.extract.pcc_progress_notes import (
    PccProgressNotesExtractor,
)
from engine.pipelines.person.ingestion.pipeline import PersonIngestionPipeline
from engine.repositories.clinical_note_repo import ClinicalNoteRepo
from engine.repositories.facility_repo import FacilityRepo
from engine.repositories.person_repo import PersonRepo
from engine.services.facility_resolver import FacilityResolver
from engine.services.person.person_service import PersonService

if typing.TYPE_CHECKING:
    from sqlmodel import Session

    from engine.pipelines.person.ingestion.transformer import (
        PersonTransformationResult,
    )


class ReadableNCPUpload(typing.Protocol):
    """Minimal uploaded-file interface required by ncp import."""

    filename: str | None

    async def read(self) -> bytes:
        """Return the uploaded file contents."""
        ...


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
        facility_resolver = FacilityResolver(FacilityRepo(session))
        person_service = PersonService(
            PersonRepo(session),
            facility_resolver,
        )
        clinical_note_repository = ClinicalNoteRepo(session)
        return cls(
            PersonIngestionPipeline(
                clinical_note_repository=clinical_note_repository,
                person_service=person_service,
                facility_resolver=facility_resolver,
            ),
        )

    async def run_upload(
        self,
        file: ReadableNCPUpload,
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
    "ReadableNCPUpload",
]
