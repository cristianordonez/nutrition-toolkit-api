from __future__ import annotations

import typing
from hashlib import sha256

from ntk.models.document import (
    Document,
    DocumentChunk,
    DocumentType,
    StoredDocumentType,
)

from .processors import (
    AssessmentProcessor,
    BaseProcessor,
    DietManualProcessor,
    IngestionProcessor,
    NutritionCareManualProcessor,
    PatientDataProcessor,
    PccOrderListReportProcessor,
    PccProgressReportProcessor,
    PccWeightHistoryReportProcessor,
    PccWeightVitalsSummaryProcessor,
)

if typing.TYPE_CHECKING:
    import pathlib

    from ntk.repositories.document_repo import DocumentRepo
    from ntk.services.open_ai_service import OpenAIService


class DocumentService:
    """Coordinate document processors and persistence."""

    def __init__(
        self,
        repository: DocumentRepo | None = None,
        open_ai_service: OpenAIService | None = None,
    ) -> None:
        """Init base class.

        :param repository: repo for db access to document table, defaults to None
        :param open_ai_service: Service class for access to OpenAI, defaults to None
        """
        self.repository = repository
        self.open_ai_service = open_ai_service

    def ingest(
        self,
        path: pathlib.Path,
        document_type: DocumentType,
        *,
        overwrite: bool = False,
    ) -> Document:
        """Validate, chunk, embed, and persist one ingestible document."""
        processor = self.get_processor(document_type, path)
        processor.validate()
        document = self.create_document(path, document_type)
        existing_document = self.find_existing_document(document)
        if existing_document is not None and not overwrite:
            return existing_document
        chunks = self.extract_chunks(processor, document)
        embeddings = self.create_embeddings(chunks)
        return self.persist(document, chunks, embeddings, overwrite=overwrite)

    @staticmethod
    def create_document(
        path: pathlib.Path,
        document_type: DocumentType,
    ) -> Document:
        """Create a persistence model from file identity only."""
        if not path.is_file():
            msg = f"Document file does not exist: {path}"
            raise ValueError(msg)
        try:
            stored_document_type = StoredDocumentType(document_type.value)
        except ValueError as error:
            msg = f"{document_type.value} does not support ingestion"
            raise ValueError(msg) from error
        return Document(
            filename=path.name,
            document_type=stored_document_type,
            file_hash=sha256(path.read_bytes()).hexdigest(),
        )

    @staticmethod
    def extract_chunks(
        processor: BaseProcessor,
        document: Document,
    ) -> list[DocumentChunk]:
        """Create chunks with an ingestion-capable processor."""
        if not isinstance(processor, IngestionProcessor):
            msg = f"{processor.document_type.value} does not support chunking"
            raise TypeError(msg)
        return processor.create_chunks(document)

    def create_embeddings(
        self,
        chunks: list[DocumentChunk],
    ) -> list[list[float]]:
        """Create one embedding for every chunk."""
        return IngestionProcessor.create_embeddings(chunks, self._open_ai_service())

    def persist(
        self,
        document: Document,
        chunks: list[DocumentChunk],
        embeddings: list[list[float]],
        *,
        overwrite: bool,
    ) -> Document:
        """Persist a processed document and its retrieval data."""
        repository = self._repository()
        return repository.ingest(
            document,
            chunks,
            embeddings,
            self._open_ai_service().embedding_model,
            overwrite=overwrite,
        )

    def find_existing_document(self, document: Document) -> Document | None:
        """Return a previously ingested document with the same identity."""
        return self._repository().find_existing_document(
            document.document_type,
            document.file_hash,
        )

    @staticmethod
    def get_processor(
        document_type: DocumentType,
        path: pathlib.Path,
    ) -> BaseProcessor:
        """Return the path-based processor for one of seven document types."""
        processor_types: dict[DocumentType, type[BaseProcessor]] = {
            DocumentType.PCC_PROGRESS_REPORT: PccProgressReportProcessor,
            DocumentType.ASSESSMENT: AssessmentProcessor,
            DocumentType.DIET_MANUAL: DietManualProcessor,
            DocumentType.NUTRITION_CARE_MANUAL: NutritionCareManualProcessor,
            DocumentType.PCC_WEIGHT_HISTORY_REPORT: PccWeightHistoryReportProcessor,
            DocumentType.PCC_ORDER_LIST_REPORT: PccOrderListReportProcessor,
            DocumentType.PCC_WEIGHT_VITALS_SUMMARY: PccWeightVitalsSummaryProcessor,
        }
        try:
            processor_type = processor_types[document_type]
        except KeyError as error:
            msg = f"Unsupported document type: {document_type.value}"
            raise ValueError(msg) from error
        return processor_type(path)

    def extract_patient_data(
        self,
        path: pathlib.Path,
        document_type: DocumentType,
    ) -> None:
        """Validate a patient report and reserve its future extraction workflow."""
        processor = self.get_processor(document_type, path)
        processor.validate()
        if not isinstance(processor, PatientDataProcessor):
            msg = f"{document_type.value} does not support patient extraction"
            raise TypeError(msg)
        processor.extract_patient_data()

    def _repository(self) -> DocumentRepo:
        if self.repository is None:
            msg = "A document repository is required for ingestion"
            raise RuntimeError(msg)
        return self.repository

    def _open_ai_service(self) -> OpenAIService:
        if self.open_ai_service is None:
            from ntk.services.open_ai_service import OpenAIService  # noqa: PLC0415

            self.open_ai_service = OpenAIService()
        return self.open_ai_service
