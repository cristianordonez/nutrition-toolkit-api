"""Extract text from PDF documents for retrieval-augmented generation."""

from __future__ import annotations

import logging
import pathlib  # noqa: TC003

from pydantic import BaseModel, Field

from ntk.controllers.base import BaseController
from ntk.database.db import get_session
from ntk.models.base import ConsoleRenderableModel
from ntk.models.document import Document, StoredDocumentType  # noqa: TC001
from ntk.models.output import Output
from ntk.repositories.document_repo import DocumentRepo
from ntk.services.document import DocumentService, DocumentType

logger = logging.getLogger(__name__)


class IngestOptions(BaseModel):
    """Input for ingesting a PDF or text file or the files in a directory."""

    path: pathlib.Path = Field(
        description="Text file or PDF file or directory containing PDF files",
    )
    document_type: StoredDocumentType = Field(
        description="Document category used to select the ingestion processor",
    )
    overwrite: bool = Field(
        default=False,
        description="Replace and re-embed a document that is already ingested",
    )


class IngestResponse(ConsoleRenderableModel):
    """Returns all Documents ingested."""

    documents: list[Document]

    def to_console(self) -> str:
        """Render the extracted documents for the CLI."""
        return "\n".join(f"# {document.filename}" for document in self.documents)


class IngestController(BaseController):
    """Ingest a PDF file or every PDF in a folder."""

    name = "ingest"
    help = "Ingest a PDF or text file or list of files in a folder"
    options_model = IngestOptions

    def __init__(
        self,
        repository: DocumentRepo | None = None,
    ) -> None:
        """Initialize the controller with optional persistence."""
        self.repository = repository

    def run(self, options: IngestOptions) -> Output:
        """Read, chunk, and persist PDFs or text files from ``options.path``."""
        file_paths = self._get_file_paths(options.path)
        session_generator = None
        repository = self.repository
        if repository is None:
            session_generator = get_session()
            repository = DocumentRepo(next(session_generator))

        try:
            service = DocumentService(repository=repository)
            documents = [
                service.ingest(
                    path,
                    DocumentType(options.document_type),
                    overwrite=options.overwrite,
                )
                for path in file_paths
            ]
            return Output(
                result=IngestResponse(documents=documents),
                controller=self.name,
                exit_code=0,
            )
        finally:
            if session_generator is not None:
                session_generator.close()

    @staticmethod
    def _get_file_paths(path: pathlib.Path) -> list[pathlib.Path]:
        """Return the PDF file represented by ``path`` or contained in it."""
        if path.is_file():
            if path.suffix.lower() in [".pdf", ".txt"]:
                return [path]
            msg = f"Path is not a PDF or text file: {path}"
            raise ValueError(msg)
        if path.is_dir():
            return sorted(
                child
                for child in path.iterdir()
                if child.is_file() and child.suffix.lower() in [".pdf", ".txt"]
            )
        msg = f"File path does not exist: {path}"
        raise ValueError(msg)
