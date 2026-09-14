from __future__ import annotations

import asyncio
import typing
from datetime import date
from types import SimpleNamespace

import pymupdf
import pytest

from ntk.models.sql.person import NutritionCareProcessSource, PersonClinicalNote
from ntk.pipelines.ncp.ingest.import_pipeline import (
    InvalidClinicalNoteReportError,
    NCPImportPipeline,
)

if typing.TYPE_CHECKING:
    import pathlib


def _write_pdf(path: pathlib.Path, text: str) -> None:
    with pymupdf.open() as document:
        page = document.new_page()
        page.insert_text((72, 72), text)
        document.save(path)


def test_import_pipeline_ingests_before_synchronizing(
    tmp_path: pathlib.Path,
) -> None:
    report = tmp_path / "progress-notes.pdf"
    _write_pdf(report, "Progress Notes *NEW*")
    assessment = PersonClinicalNote(
        person_id=1,
        note_text="Nutrition assessment",
        raw_text="Nutrition assessment",
        note_key="imported-ncp-1",
        content_hash="hash",
        note_date=date(2026, 8, 28),
        created_by="dietitian",
        ncp_source=NutritionCareProcessSource.IMPORTED,
    )
    events: list[str] = []

    class IngestionPipeline:
        @staticmethod
        async def ingest(paths: list[pathlib.Path]) -> None:
            assert paths == [report]
            events.append("notes ingested")

    class NutritionCareProcessPipeline:
        @staticmethod
        async def sync_ncps() -> object:
            assert events == ["notes ingested"]
            events.append("assessments synchronized")
            return SimpleNamespace(created_ncps=[assessment])

    result = asyncio.run(
        NCPImportPipeline(
            IngestionPipeline(),  # ty: ignore[invalid-argument-type]
            NutritionCareProcessPipeline(),  # ty: ignore[invalid-argument-type]
        ).run(report),
    )

    assert events == ["notes ingested", "assessments synchronized"]
    assert result == [assessment]


def test_import_pipeline_rejects_non_pdf(tmp_path: pathlib.Path) -> None:
    report = tmp_path / "progress-notes.txt"
    report.touch()

    with pytest.raises(ValueError, match="is not a PDF"):
        asyncio.run(
            NCPImportPipeline(
                object(),  # ty: ignore[invalid-argument-type]
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
                object(),  # ty: ignore[invalid-argument-type]
            ).run(report),
        )
