"""Ingest diet and nutrition care manuals."""

from __future__ import annotations

import pathlib  # noqa: TC003
import typing

from pydantic import BaseModel, Field

from engine.controllers.base import BaseController
from engine.controllers.session import controller_session
from engine.controllers.uploads import (
    ReadableUpload,
    UploadRequirements,
    materialize_uploads,
)
from engine.models.base import ConsoleRenderableModel
from engine.models.knowledge import KnowledgeIngestResponsePublic
from engine.models.output import Output
from engine.models.sql.knowledge import Knowledge, KnowledgeType  # noqa: TC001
from engine.pipelines.knowledge.ingestion.pipeline import KnowledgeIngestionPipeline
from engine.repositories.knowledge_repo import KnowledgeRepo
from engine.services.embedding_service import (
    DEFAULT_EMBEDDING_MODEL,
    EmbeddingService,
)

if typing.TYPE_CHECKING:
    from sqlmodel import Session


class KnowledgeIngestOptions(BaseModel):
    """Options for ingesting clinical knowledge documents."""

    path: pathlib.Path = Field(description="Manual PDF, text file, or directory")
    document_type: KnowledgeType = Field(
        description="Knowledge document type, diet-manual or nutrition-care-manual",
    )
    overwrite: bool = Field(default=False, description="Replace existing documents")


class KnowledgeIngestResponse(ConsoleRenderableModel):
    """Knowledge documents ingested into retrieval storage."""

    documents: list[Knowledge]

    def to_console(self) -> str:
        """Render the ingested document names and total chunk count."""
        lines = [f"# {document.filename}" for document in self.documents]
        chunk_count = sum(len(document.chunks) for document in self.documents)
        lines.append(f"Created {chunk_count} chunk(s).")
        return "\n".join(lines)


class KnowledgeIngestController(BaseController):
    """Store knowledge documents and their embeddings."""

    name = "ingest"
    help = "Ingest a diet or nutrition care manual"
    options_model = KnowledgeIngestOptions

    def __init__(self, session: Session | None = None) -> None:
        """Use an injected session or create one for each controller run."""
        self.session = session

    async def run_uploads(
        self,
        files: typing.Sequence[ReadableUpload],
        document_type: KnowledgeType,
        *,
        overwrite: bool = False,
    ) -> Output[KnowledgeIngestResponsePublic]:
        """Validate uploaded knowledge files and ingest their chunks."""
        async with materialize_uploads(
            files,
            UploadRequirements(
                allowed_suffixes=frozenset({".pdf", ".txt"}),
                file_description="PDF or text file",
                directory_prefix="ntk-rag-",
                default_filename=lambda index: f"upload-{index}.pdf",
            ),
        ) as uploads:
            output = await self.run(
                KnowledgeIngestOptions(
                    path=uploads.directory,
                    document_type=document_type,
                    overwrite=overwrite,
                ),
            )
            return Output(
                result=KnowledgeIngestResponsePublic.from_documents(
                    output.result.documents,
                ),
                controller=output.controller,
                exit_code=output.exit_code,
            )

    async def run(
        self,
        options: KnowledgeIngestOptions,
    ) -> Output[KnowledgeIngestResponse]:
        """Ingest the selected knowledge document type."""
        paths = self._get_file_paths(options.path)
        with controller_session(self.session) as session:
            repository = KnowledgeRepo(session, DEFAULT_EMBEDDING_MODEL)
            embedding_service = EmbeddingService(session)
            service = KnowledgeIngestionPipeline(
                knowledge_repository=repository,
                embedding_service=embedding_service,
            )
            documents = [
                await service.ingest_knowledge(
                    path,
                    options.document_type,
                    overwrite=options.overwrite,
                )
                for path in paths
            ]
            for document in documents:
                _ = (
                    document.id,
                    document.filename,
                    document.knowledge_type,
                    document.file_hash,
                    document.synced_at,
                    tuple(document.chunks),
                )
            return Output(
                result=KnowledgeIngestResponse(documents=documents),
                controller=self.name,
                exit_code=0,
            )

    @staticmethod
    def _get_file_paths(path: pathlib.Path) -> list[pathlib.Path]:
        """Return a supported file or supported files within a directory."""
        if path.is_file():
            if path.suffix.lower() in {".pdf", ".txt"}:
                return [path]
            msg = f"Path is not a PDF or text file: {path}"
            raise ValueError(msg)
        if path.is_dir():
            return sorted(
                child
                for child in path.iterdir()
                if child.is_file() and child.suffix.lower() in {".pdf", ".txt"}
            )
        msg = f"File path does not exist: {path}"
        raise ValueError(msg)
