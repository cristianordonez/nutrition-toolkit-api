from __future__ import annotations

import asyncio
import typing
from datetime import date

import pytest

from ntk.controllers.ncp import import_ncps as import_module
from ntk.controllers.ncp.import_ncps import (
    NCPImportController,
    NCPImportOptions,
)
from ntk.models.sql.person import NutritionCareProcessSource, PersonClinicalNote
from ntk.pipelines.ncp.ingest.import_pipeline import (
    InvalidClinicalNoteReportError,
)

if typing.TYPE_CHECKING:
    import pathlib


class Upload:
    def __init__(self, filename: str) -> None:
        self.filename: str | None = filename

    async def read(self) -> bytes:
        return b"pdf"


def test_import_command_ingests_notes_then_synchronizes_assessments(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report = tmp_path / "progress-notes.pdf"
    report.touch()
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

    class Pipeline:
        @classmethod
        def from_session(cls, session: object) -> Pipeline:
            assert session == "session"
            return cls()

        @staticmethod
        async def run(path: pathlib.Path) -> list[PersonClinicalNote]:
            assert path == report
            return [assessment]

    monkeypatch.setattr(import_module, "NCPImportPipeline", Pipeline)

    output = asyncio.run(
        NCPImportController(
            session="session",  # ty: ignore[invalid-argument-type]
        ).run(NCPImportOptions(path=report)),
    )

    assert output.result.ncps == [assessment]
    assert output.result.to_console() == str(assessment.id)


def test_import_command_rejects_non_pdf(tmp_path: pathlib.Path) -> None:
    report = tmp_path / "progress-notes.txt"
    report.touch()

    with pytest.raises(ValueError, match="is not a PDF"):
        asyncio.run(
            NCPImportController(
                session="session",  # ty: ignore[invalid-argument-type]
            ).run(NCPImportOptions(path=report)),
        )


def test_import_uploads_continues_after_invalid_clinical_note_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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

    class Pipeline:
        @classmethod
        def from_session(cls, session: object) -> Pipeline:
            assert session == "session"
            return cls()

        @staticmethod
        async def run_upload(
            file: Upload,
            *,
            overwrite: bool,
            created_by: str | None,
        ) -> list[PersonClinicalNote]:
            assert overwrite is True
            assert created_by == "dietitian"
            if file.filename == "orders.pdf":
                message = "'orders.pdf' is not a PCC progress-note report"
                raise InvalidClinicalNoteReportError(message)
            return [assessment]

    monkeypatch.setattr(import_module, "NCPImportPipeline", Pipeline)

    output = asyncio.run(
        NCPImportController(
            session="session",  # ty: ignore[invalid-argument-type]
        ).run_uploads(
            [Upload("orders.pdf"), Upload("progress-notes.pdf")],
            overwrite=True,
            created_by="dietitian",
        ),
    )

    assert output.result.ncps == [assessment]
    assert len(output.result.failures) == 1
    assert output.result.failures[0].filename == "orders.pdf"
    assert "not a PCC progress-note report" in output.result.failures[0].detail
