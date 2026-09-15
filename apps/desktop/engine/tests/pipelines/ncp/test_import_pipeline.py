from __future__ import annotations

import asyncio
import typing

import pymupdf
import pytest

from engine.models.sql.document import Document
from engine.pipelines.ncp.ingest.import_pipeline import (
    InvalidClinicalNoteReportError,
    NCPImportPipeline,
)
from engine.pipelines.person.ingestion.transformer import (
    PersonTransformationResult,
    TransformedDocument,
)

if typing.TYPE_CHECKING:
    import pathlib


def _write_pdf(path: pathlib.Path, text: str) -> None:
    with pymupdf.open() as document:
        page = document.new_page()
        page.insert_text((72, 72), text)
        document.save(path)


def _transformed_document(filename: str) -> TransformedDocument:
    return TransformedDocument(
        document=Document(
            filename=filename,
            file_type="pdf",
            checksum=filename,
            storage_uri=filename,
            document_type="clinical-note",
        ),
        document_sources=[],
        extracted_facts=[],
        related_models=[],
    )


def test_import_pipeline_ingests_a_clinical_note_report(
    tmp_path: pathlib.Path,
) -> None:
    report = tmp_path / "progress-notes.pdf"
    _write_pdf(report, "Progress Notes *NEW*")

    class IngestionService:
        @staticmethod
        async def ingest(paths: list[pathlib.Path]) -> PersonTransformationResult:
            assert paths == [report]
            return PersonTransformationResult(
                documents=[_transformed_document("progress-notes.pdf")],
            )

    result = asyncio.run(
        NCPImportPipeline(
            IngestionService(),  # ty: ignore[invalid-argument-type]
        ).run(report),
    )

    assert len(result.documents) == 1
    assert result.documents[0].document.filename == "progress-notes.pdf"


def test_import_pipeline_rejects_non_pdf(tmp_path: pathlib.Path) -> None:
    report = tmp_path / "progress-notes.txt"
    report.touch()

    with pytest.raises(InvalidClinicalNoteReportError, match="is not a PDF"):
        asyncio.run(
            NCPImportPipeline(
                object(),  # ty: ignore[invalid-argument-type]
            ).run(report),
        )


def test_import_pipeline_rejects_pdf_that_is_not_clinical_note_report(
    tmp_path: pathlib.Path,
) -> None:
    report = tmp_path / "orders.pdf"
    _write_pdf(report, "Order Listing Report")

    with pytest.raises(
        InvalidClinicalNoteReportError,
        match="is not a PCC clinical-note report",
    ):
        asyncio.run(
            NCPImportPipeline(
                object(),  # ty: ignore[invalid-argument-type]
            ).run(report),
        )
