"""Ingest uploaded documents into the database."""

from __future__ import annotations

import dataclasses
import pathlib
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
from engine.models.output import Output
from engine.pipelines.person.ingestion.failure_recorder import (
    IngestionFailureRecorder,
)
from engine.pipelines.person.ingestion.pipeline import PersonIngestionPipeline
from engine.pipelines.person.ingestion.transformer import (
    ClinicalFactTransformer,
    PersonTransformationResult,
)
from engine.repositories.clinical_source_repo import ClinicalSourceRepo
from engine.repositories.person_repo import PersonRepo
from engine.services.person.person_service import PersonService

if typing.TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import date

    from sqlmodel import Session


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
    #: Extractions that failed during the run. Non-zero means this document
    #: gave up some of its content: the facts that did land are real, but the
    #: report is incomplete and re-ingesting it once the cause is fixed will
    #: recover the rest.
    extraction_failures: int = 0
    #: A few of those failures, so a reader can tell a quota problem from an
    #: unreadable page without opening the log.
    failure_samples: list[str] = Field(default_factory=list)
    #: Distinct failure messages `failure_samples` left out. Non-zero means the
    #: samples are not the whole story and the log has causes they do not name.
    unshown_failure_messages: int = 0

    @classmethod
    def from_transformation(
        cls,
        result: PersonTransformationResult,
        failures: IngestionFailureRecorder | None = None,
    ) -> DocumentIngestResult:
        """Summarize a completed transformation."""
        return cls(
            extraction_failures=failures.count if failures else 0,
            failure_samples=failures.samples if failures else [],
            unshown_failure_messages=(failures.unshown_messages if failures else 0),
            documents=len(result.documents),
            facts=sum(len(document.clinical_facts) for document in result.documents),
            person_ids=sorted(
                {
                    fact.person_id
                    for document in result.documents
                    for fact in document.clinical_facts
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
        """Materialize uploads and run the document ETL pipeline.

        The run happens inside a failure recorder so a partial extraction --
        pages the model could not read, a spent quota part-way through -- is
        reported rather than hidden behind the facts that did land.
        """
        with IngestionFailureRecorder() as failures:
            result = await self._ingest(options)
        return Output(
            result=DocumentIngestResult.from_transformation(result, failures),
            controller=self.name,
            exit_code=0,
        )

    async def _ingest(
        self,
        options: DocumentIngestOptions,
    ) -> PersonTransformationResult:
        """Materialize the uploads and run the pipeline over them."""
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
                    ClinicalFactTransformer.document_checksum(path): path
                    for path in uploads.paths
                }.values(),
            )
            # A batch deliberately shares one session and one pipeline. Separate
            # worker sessions can race while resolving people and inserting rows
            # protected by SQLite uniqueness constraints. Extractors keep their
            # own bounded model-call concurrency where they support it.
            with controller_session(self.session) as session:
                person_service = PersonService(PersonRepo(session))
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
                    clinical_source_repository=ClinicalSourceRepo(session),
                    person_service=person_service,
                )
                result = await service.ingest(
                    files=paths,
                    person_id=options.person_id,
                    source_person_name=known_person_name,
                    date_of_birth=known_date_of_birth,
                )
        return result


__all__ = [
    "DocumentIngestController",
    "DocumentIngestOptions",
    "DocumentIngestResult",
]
