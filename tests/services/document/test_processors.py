from __future__ import annotations

import typing
from datetime import date

import pytest

from ntk.models.document import ChunkType, DocumentType
from ntk.services.document import DocumentService
from ntk.services.document.processors import (
    AssessmentProcessor,
    DietManualProcessor,
    PccProgressReportProcessor,
    PccWeightHistoryReportProcessor,
)
from ntk.services.document.processors.knowledge_processor import MAX_CHUNK_TOKENS

if typing.TYPE_CHECKING:
    import pathlib


class FakeOpenAIService:
    def __init__(self) -> None:
        self.contents: list[str] = []

    def create_embedding(self, content: str) -> list[float]:
        self.contents.append(content)
        return [float(len(content))]


def test_assessment_processor_reads_source_and_creates_chunk(
    tmp_path: pathlib.Path,
) -> None:
    path = tmp_path / "assessment.txt"
    path.write_text(" Nutrition assessment ", encoding="utf-8")
    processor = AssessmentProcessor(path)
    document = DocumentService.create_document(path, DocumentType.ASSESSMENT)

    processor.validate()
    chunks = DocumentService.extract_chunks(processor, document)

    assert [chunk.content for chunk in chunks] == ["Nutrition assessment"]
    assert chunks[0].chunk_type is ChunkType.ASSESSMENT


def test_processor_creates_one_embedding_per_chunk(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "assessment.txt"
    path.write_text("Nutrition assessment", encoding="utf-8")
    processor = AssessmentProcessor(path)
    document = DocumentService.create_document(path, DocumentType.ASSESSMENT)
    chunks = DocumentService.extract_chunks(processor, document)
    service = FakeOpenAIService()

    embeddings = processor.create_embeddings(chunks, service)  # ty: ignore[invalid-argument-type]

    assert embeddings == [[20.0]]
    assert service.contents == ["Nutrition assessment"]


def test_manual_processor_splits_oversized_text(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "manual.txt"
    path.write_text(
        "Diet Manual\n\n"
        + "\n\n".join(
            f"Paragraph {index}. " + "nutrition " * 100 for index in range(12)
        ),
        encoding="utf-8",
    )
    processor = DietManualProcessor(path)
    document = DocumentService.create_document(path, DocumentType.DIET_MANUAL)

    processor.validate()
    chunks = DocumentService.extract_chunks(processor, document)

    assert len(chunks) > 1
    assert all(
        processor._token_count(chunk.content) <= MAX_CHUNK_TOKENS  # noqa: SLF001
        for chunk in chunks
    )
    assert all(chunk.chunk_type is ChunkType.DIET_MANUAL for chunk in chunks)


def test_progress_processor_extracts_assessment_chunks(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "progress.pdf"
    path.touch()
    processor = PccProgressReportProcessor(path)
    processor.__dict__["page_texts"] = [
        (
            "Effective Date: 08/18/2026 10:30 Type: Nutrition Assessment\n"
            "Note Text: Patient improved\nAuthor: Dietitian"
        ),
    ]
    document = DocumentService.create_document(path, DocumentType.PCC_PROGRESS_REPORT)

    processor.validate()
    chunks = DocumentService.extract_chunks(processor, document)

    assert [chunk.content for chunk in chunks] == ["Note Text: Patient improved"]
    assert chunks[0].chunk_metadata["assessment_date"] == date(2026, 8, 18)
    assert chunks[0].chunk_type is ChunkType.ASSESSMENT


def test_patient_processor_exposes_future_extraction_placeholder(
    tmp_path: pathlib.Path,
) -> None:
    path = tmp_path / "weights.txt"
    path.write_text("Weight History", encoding="utf-8")
    processor = PccWeightHistoryReportProcessor(path)

    processor.validate()
    assert processor.extract_patient_data() is None


def test_processor_validation_rejects_wrong_format(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "assessment.txt"
    path.write_text("unrelated document", encoding="utf-8")

    with pytest.raises(ValueError, match="does not match"):
        AssessmentProcessor(path).validate()
