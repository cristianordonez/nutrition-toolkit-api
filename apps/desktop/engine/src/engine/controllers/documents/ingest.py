"""Ingest uploaded documents into the database."""

from __future__ import annotations

import asyncio
import dataclasses
import pathlib
import typing

from pydantic import BaseModel

from engine.controllers.session import controller_session
from engine.models.settings import SETTINGS
from engine.pipelines.person.ingestion.pipeline import PersonIngestionPipeline
from engine.pipelines.person.ingestion.transformer import (
    ExtractedFactTransformer,
    PersonTransformationResult,
)
from engine.repositories.clinical_note_repo import ClinicalNoteRepo
from engine.repositories.facility_repo import FacilityRepo
from engine.repositories.person_repo import PersonRepo
from engine.services.facility_resolver import FacilityResolver
from engine.services.person.person_service import PersonService
from ntk.controllers.base import BaseController
from ntk.controllers.uploads import (
    ReadableUpload,
    UploadRequirements,
    materialize_uploads,
)
from ntk.models.base import ConsoleRenderableModel
from ntk.models.output import Output
from ntk.utils.parallel import ParallelPoolHandler

if typing.TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import date

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
            clinical_note_repository=ClinicalNoteRepo(session),
            person_service=person_service,
            facility_resolver=facility_resolver,
        )
        return asyncio.run(service.ingest(files=[path]))


@dataclasses.dataclass(frozen=True, slots=True)
class LocalFileUpload:
    """Adapt a file on disk to the upload protocol the pipeline expects.

    The CLI (and the desktop app behind it) supplies paths, while the upload
    machinery was written for request uploads. Wrapping here keeps one
    ingestion path for both.
    """

    path: pathlib.Path

    @property
    def filename(self) -> str:
        """Return the file's name."""
        return self.path.name

    async def read(self) -> bytes:
        """Return the file's contents."""
        return self.path.read_bytes()


def _as_uploads(files: Sequence[typing.Any]) -> list[typing.Any]:
    """Wrap any plain path in `files`, leaving real uploads untouched."""
    return [
        LocalFileUpload(pathlib.Path(file))
        if isinstance(file, (str, pathlib.Path))
        else file
        for file in files
    ]


class DocumentIngestOptions(BaseModel):
    """Documents supplied to the ingestion workflow."""

    files: list[typing.Any]
    # Pins an unknown (non-deterministically-recognized) document to an
    # already-identified resident, e.g. a person-scoped upload where the
    # document alone may not unambiguously identify who it belongs to.
    person_id: int | None = None


class DocumentIngestResult(ConsoleRenderableModel):
    """What one ingestion run persisted.

    A summary rather than the raw ``PersonTransformationResult``: callers need
    to know how much landed and who it was attributed to, and the full
    transformation tree is both large and internal.
    """

    documents: int
    facts: int
    person_ids: list[int]

    @classmethod
    def from_transformation(
        cls,
        result: PersonTransformationResult,
    ) -> DocumentIngestResult:
        """Summarize a completed transformation."""
        return cls(
            documents=len(result.documents),
            facts=sum(len(document.extracted_facts) for document in result.documents),
            person_ids=sorted(
                {
                    fact.person_id
                    for document in result.documents
                    for fact in document.extracted_facts
                    if fact.person_id is not None
                },
            ),
        )

    def to_console(self) -> str:
        """Render the ingestion summary as JSON."""
        return self.model_dump_json(indent=2)


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
    ) -> Output[DocumentIngestResult]:
        """Materialize uploads and run the document ETL pipeline."""
        async with materialize_uploads(
            typing.cast("Sequence[ReadableUpload]", _as_uploads(options.files)),
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
            if (
                self.session is not None
                or len(paths) == 1
                or options.person_id is not None
            ):
                with controller_session(self.session) as session:
                    facility_resolver = FacilityResolver(FacilityRepo(session))
                    person_service = PersonService(
                        PersonRepo(session),
                        facility_resolver,
                    )
                    known_person_name: str | None = None
                    known_date_of_birth: date | None = None
                    if options.person_id is not None:
                        person = person_service.repository.get_by_id(
                            options.person_id,
                        )
                        if person is None:
                            msg = f"Person {options.person_id} was not found"
                            raise LookupError(msg)
                        known_person_name = person.name
                        known_date_of_birth = person.date_of_birth
                    service = PersonIngestionPipeline(
                        clinical_note_repository=ClinicalNoteRepo(session),
                        person_service=person_service,
                        facility_resolver=facility_resolver,
                    )
                    result = await service.ingest(
                        files=paths,
                        person_id=options.person_id,
                        source_person_name=known_person_name,
                        date_of_birth=known_date_of_birth,
                    )
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
        return Output(
            result=DocumentIngestResult.from_transformation(result),
            controller=self.name,
            exit_code=0,
        )


__all__ = [
    "DocumentIngestController",
    "DocumentIngestOptions",
    "DocumentIngestResult",
]
