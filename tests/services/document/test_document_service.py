from __future__ import annotations

import typing

import pytest

from ntk.services.document import DocumentService, DocumentType
from ntk.services.document.processors import (
    AssessmentProcessor,
    DietManualProcessor,
    NutritionCareManualProcessor,
    PccOrderListReportProcessor,
    PccProgressReportProcessor,
    PccWeightHistoryReportProcessor,
    PccWeightVitalsSummaryProcessor,
)

if typing.TYPE_CHECKING:
    import pathlib
    from collections.abc import Sequence
    from uuid import UUID

    from ntk.models.document import Document, DocumentChunk, StoredDocumentType


class FakeOpenAIService:
    embedding_model = "embedding-model"

    def __init__(self) -> None:
        self.contents: list[str] = []

    def create_embedding(self, content: str) -> list[float]:
        self.contents.append(content)
        return [0.1, 0.2]


class FakeDocumentRepo:
    def __init__(self, existing: Document | None = None) -> None:
        self.existing = existing
        self.ingested: (
            tuple[Document, list[DocumentChunk], list[list[float]], str] | None
        ) = None

    def find_existing_document(
        self,
        document_type: StoredDocumentType,
        file_hash: str,
    ) -> Document | None:
        del document_type, file_hash
        return self.existing

    def count_chunks(self, document_id: UUID) -> int:
        del document_id
        return 1

    def ingest(
        self,
        document: Document,
        chunks: Sequence[DocumentChunk],
        embeddings: Sequence[list[float]],
        model_name: str | None,
        *,
        overwrite: bool = False,
    ) -> Document:
        del overwrite
        self.ingested = (document, list(chunks), list(embeddings), model_name)
        return document


@pytest.mark.parametrize(
    ("document_type", "processor_type"),
    [
        (DocumentType.PCC_PROGRESS_REPORT, PccProgressReportProcessor),
        (DocumentType.ASSESSMENT, AssessmentProcessor),
        (DocumentType.DIET_MANUAL, DietManualProcessor),
        (DocumentType.NUTRITION_CARE_MANUAL, NutritionCareManualProcessor),
        (DocumentType.PCC_WEIGHT_HISTORY_REPORT, PccWeightHistoryReportProcessor),
        (DocumentType.PCC_ORDER_LIST_REPORT, PccOrderListReportProcessor),
        (DocumentType.PCC_WEIGHT_VITALS_SUMMARY, PccWeightVitalsSummaryProcessor),
    ],
)
def test_ingest_selects_processor_for_document_type(
    tmp_path: pathlib.Path,
    document_type: DocumentType,
    processor_type: type,
) -> None:
    path = tmp_path / "document.txt"
    path.write_text("document content", encoding="utf-8")

    processor = DocumentService().get_processor(
        document_type,
        path,
    )

    assert isinstance(processor, processor_type)
    assert processor.text == "document content"


def test_ingest_rejects_unsupported_file_type(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "document.csv"
    path.touch()

    with pytest.raises(ValueError, match="Unsupported document file type"):
        DocumentService().ingest(
            path,
            DocumentType.ASSESSMENT,
        )


def test_ingest_creates_and_persists_all_embedding_models(
    tmp_path: pathlib.Path,
) -> None:
    path = tmp_path / "assessment.txt"
    path.write_text("Nutrition assessment", encoding="utf-8")
    repository = FakeDocumentRepo()
    open_ai_service = FakeOpenAIService()

    result = DocumentService(
        repository=repository,  # ty: ignore[invalid-argument-type]
        open_ai_service=open_ai_service,  # ty: ignore[invalid-argument-type]
    ).ingest(
        path,
        DocumentType.ASSESSMENT,
    )

    assert repository.ingested is not None
    document, chunks, embeddings, model_name = repository.ingested
    assert document.filename == "assessment.txt"
    assert [chunk.content for chunk in chunks] == ["Nutrition assessment"]
    assert embeddings == [[0.1, 0.2]]
    assert model_name == "embedding-model"
    assert open_ai_service.contents == ["Nutrition assessment"]
    assert result.id == document.id
