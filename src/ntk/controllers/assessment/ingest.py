"""Ingest completed assessments for later retrieval."""

from __future__ import annotations

import pathlib  # noqa: TC003
import typing

from pydantic import BaseModel, Field, computed_field

from ntk.controllers.base import BaseController
from ntk.controllers.uploads import (
    ReadableUpload,
    UploadRequirements,
    materialize_uploads,
)
from ntk.database.db import get_session
from ntk.models.base import ConsoleRenderableModel
from ntk.models.output import Output
from ntk.models.sql.assessment import Assessment  # noqa: TC001
from ntk.repositories.assessment_repo import AssessmentRepo
from ntk.services.document import DocumentExtractorService


class AssessmentIngestOptions(BaseModel):
    """Options for ingesting completed nutrition assessments."""

    path: pathlib.Path = Field(description="Assessment PDF, text file, or directory")
    overwrite: bool = Field(default=False, description="Replace the uploaded source")
    created_by: str = Field(default="self", description="Assessment author")


class AssessmentIngestResponse(ConsoleRenderableModel):
    """Completed assessment documents ingested for retrieval."""

    documents: list[Assessment]

    @computed_field
    @property
    def chunk_count(self) -> int:
        """Return the number of assessment chunks created."""
        return len(self.documents)

    def to_console(self) -> str:
        """Render the names of ingested assessment documents."""
        return "\n".join(
            f"# {assessment.source_filename or 'generated-assessment'}"
            for assessment in self.documents
        )


class AssessmentIngestController(BaseController):
    """Store completed assessments and their embeddings."""

    name = "ingest"
    help = "Ingest completed nutrition assessments"
    options_model = AssessmentIngestOptions

    def __init__(self, repository: AssessmentRepo | None = None) -> None:
        """Initialize with optional persistence for dependency injection."""
        self.repository = repository

    async def run_uploads(
        self,
        files: typing.Sequence[ReadableUpload],
        *,
        overwrite: bool = False,
        created_by: str = "self",
    ) -> Output[AssessmentIngestResponse]:
        """Validate uploaded assessment files and ingest their chunks."""
        async with materialize_uploads(
            files,
            UploadRequirements(
                allowed_suffixes=frozenset({".pdf"}),
                file_description="PDF file",
                directory_prefix="ntk-assessment-",
                default_filename=lambda index: f"assessment-{index}.pdf",
            ),
        ) as uploads:
            return self.run(
                AssessmentIngestOptions(
                    path=uploads.directory,
                    overwrite=overwrite,
                    created_by=created_by,
                ),
            )

    def run(
        self,
        options: AssessmentIngestOptions,
    ) -> Output[AssessmentIngestResponse]:
        """Ingest assessment documents with the fixed assessment type."""
        paths = self._get_file_paths(options.path)
        session_generator = None
        repository = self.repository
        if repository is None:
            session_generator = get_session()
            repository = AssessmentRepo(next(session_generator))
        try:
            service = DocumentExtractorService(assessment_repository=repository)
            documents = [
                assessment
                for path in paths
                for assessment in service.ingest_assessment(
                    path,
                    overwrite=options.overwrite,
                    created_by=options.created_by,
                )
            ]
            return Output(
                result=AssessmentIngestResponse(documents=documents),
                controller=self.name,
                exit_code=0,
            )
        finally:
            if session_generator is not None:
                session_generator.close()

    @staticmethod
    def _get_file_paths(path: pathlib.Path) -> list[pathlib.Path]:
        """Return a supported file or supported files within a directory."""
        if path.is_file():
            if path.suffix.lower() == ".pdf":
                return [path]
            msg = f"Path is not a PDF or text file: {path}"
            raise ValueError(msg)
        if path.is_dir():
            return sorted(
                child
                for child in path.iterdir()
                if child.is_file() and child.suffix.lower() == ".pdf"
            )
        msg = f"File path does not exist: {path}"
        raise ValueError(msg)
