"""Ingest uploaded documents into the database."""

from __future__ import annotations

import asyncio
import typing

from pydantic import BaseModel

from ntk.controllers.base import BaseController
from ntk.controllers.session import controller_session
from ntk.controllers.uploads import (
    ReadableUpload,
    UploadRequirements,
    materialize_uploads,
)
from ntk.models.output import Output
from ntk.models.settings import SETTINGS
from ntk.pipelines.person.ingestion.pipeline import PersonIngestionPipeline
from ntk.pipelines.person.ingestion.transformer import (
    ExtractedFactTransformer,
    PersonTransformationResult,
)
from ntk.repositories.facility_repo import FacilityRepo
from ntk.repositories.person_repo import PersonRepo
from ntk.repositories.progress_note_repo import ProgressNoteRepo
from ntk.services.facility_resolver import FacilityResolver
from ntk.services.person.person_service import PersonService
from ntk.utils.parallel import ParallelPoolHandler

if typing.TYPE_CHECKING:
    import pathlib
    from collections.abc import Sequence

    from sqlmodel import Session


def _ingest_document(path: pathlib.Path) -> PersonTransformationResult:
    """Ingest one path with worker-local database and service resources."""
    with controller_session(None) as session:
        facility_resolver = FacilityResolver(FacilityRepo(session))
        person_service = PersonService(
            PersonRepo(session),
            facility_resolver,
        )
        service = PersonIngestionPipeline(
            progress_note_repository=ProgressNoteRepo(session),
            person_service=person_service,
            facility_resolver=facility_resolver,
        )
        return asyncio.run(service.ingest(files=[path]))


class DocumentIngestOptions(BaseModel):
    """Documents supplied to the ingestion workflow."""

    files: list[typing.Any]


class DocumentIngestController(BaseController):
    """Validate and persist uploaded documents."""

    name = "ingest"
    help = "Ingest PDF, CSV, or text documents"
    options_model = DocumentIngestOptions

    def __init__(self, session: Session | None = None) -> None:
        """Store the optional controller-owned session."""
        self.session = session

    async def run(
        self,
        options: DocumentIngestOptions,
    ) -> Output[PersonTransformationResult]:
        """Materialize uploads and run the document ETL pipeline."""
        async with materialize_uploads(
            typing.cast("Sequence[ReadableUpload]", options.files),
            UploadRequirements(
                allowed_suffixes=frozenset({".csv", ".pdf", ".txt"}),
                file_description="PDF, CSV, or text file",
                directory_prefix="ntk-document-",
                default_filename=lambda index: f"document-{index + 1}.pdf",
                reject_empty=True,
            ),
        ) as uploads:
            paths = list(
                {
                    ExtractedFactTransformer.document_checksum(path): path
                    for path in uploads.paths
                }.values(),
            )
            if self.session is not None or len(paths) == 1:
                with controller_session(self.session) as session:
                    facility_resolver = FacilityResolver(FacilityRepo(session))
                    person_service = PersonService(
                        PersonRepo(session),
                        facility_resolver,
                    )
                    service = PersonIngestionPipeline(
                        progress_note_repository=ProgressNoteRepo(session),
                        person_service=person_service,
                        facility_resolver=facility_resolver,
                    )
                    result = await service.ingest(files=paths)
            else:
                handler = ParallelPoolHandler(
                    mode=SETTINGS.document_ingestion_pool_mode,
                    workers=SETTINGS.document_ingestion_workers,
                )
                results = typing.cast(
                    "list[PersonTransformationResult]",
                    await asyncio.to_thread(
                        handler.map,
                        _ingest_document,
                        paths,
                    ),
                )
                result = PersonTransformationResult(
                    documents=[
                        document
                        for worker_result in results
                        for document in worker_result.documents
                    ],
                )
        return Output(result=result, controller=self.name, exit_code=0)


__all__ = ["DocumentIngestController", "DocumentIngestOptions"]
