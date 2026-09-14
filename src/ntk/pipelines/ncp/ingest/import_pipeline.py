"""Workflow for importing Nutrition Care Processes from clinical-note reports."""

from __future__ import annotations

import pathlib
import typing
from tempfile import TemporaryDirectory

from ntk.pipelines.ncp.create.pipeline import NutritionCareProcessPipeline
from ntk.pipelines.person.ingestion.extract.pcc_progress_notes import (
    PccProgressNotesExtractor,
)
from ntk.pipelines.person.ingestion.pipeline import PersonIngestionPipeline
from ntk.repositories.clinical_note_repo import ClinicalNoteRepo
from ntk.repositories.facility_repo import FacilityRepo
from ntk.repositories.person_repo import PersonRepo
from ntk.services.facility_resolver import FacilityResolver
from ntk.services.person.person_service import PersonService

if typing.TYPE_CHECKING:
    from sqlmodel import Session

    from ntk.models.sql.person import PersonClinicalNote


class ReadableNCPUpload(typing.Protocol):
    """Minimal uploaded-file interface required by ncp import."""

    filename: str | None

    async def read(self) -> bytes:
        """Return the uploaded file contents."""
        ...


class InvalidClinicalNoteReportError(ValueError):
    """Raised when an ncp-import file is not a PCC clinical-note report."""


class NCPImportPipeline:
    """Ingest clinical notes and synchronize their Nutrition Care Processes."""

    def __init__(
        self,
        ingestion_service: PersonIngestionPipeline,
        ncp_pipeline: NutritionCareProcessPipeline,
    ) -> None:
        """Store the two workflows that comprise ncp import."""
        self.ingestion_service = ingestion_service
        self.ncp_pipeline = ncp_pipeline

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
            NutritionCareProcessPipeline(
                clinical_note_repository,
            ),
        )

    async def run_upload(
        self,
        file: ReadableNCPUpload,
        *,
        overwrite: bool = False,
        created_by: str | None = None,
    ) -> list[PersonClinicalNote]:
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

    async def run(self, path: pathlib.Path) -> list[PersonClinicalNote]:
        """Ingest one clinical-note PDF and return newly synchronized ncps."""
        self._validate_report_path(path)
        self._validate_clinical_note_report(path)
        await self.ingestion_service.ingest([path])
        sync_result = await self.ncp_pipeline.sync_ncps()
        return sync_result.created_ncps

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
