from __future__ import annotations

import asyncio
import typing

import pytest

from engine.controllers.ncp import import_ncps as import_module
from engine.controllers.ncp.import_ncps import (
    NCPImportController,
    NCPImportOptions,
)
from engine.models.sql.document import Document
from engine.pipelines.ncp.ingest.import_pipeline import (
    InvalidClinicalNoteReportError,
)
from engine.pipelines.person.ingestion.transformer import (
    PersonTransformationResult,
    TransformedDocument,
)

if typing.TYPE_CHECKING:
    import pathlib


class Upload:
    def __init__(self, filename: str) -> None:
        self.filename: str | None = filename

    async def read(self) -> bytes:
        return b"pdf"


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


def test_import_command_ingests_the_report(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report = tmp_path / "progress-notes.pdf"
    report.touch()

    class Pipeline:
        @classmethod
        def from_session(cls, session: object) -> Pipeline:
            assert session == "session"
            return cls()

        @staticmethod
        async def run(path: pathlib.Path) -> PersonTransformationResult:
            assert path == report
            return PersonTransformationResult(
                documents=[
                    _transformed_document("a.pdf"),
                    _transformed_document("b.pdf"),
                ],
            )

    monkeypatch.setattr(import_module, "NCPImportPipeline", Pipeline)

    output = asyncio.run(
        NCPImportController(
            session="session",  # ty: ignore[invalid-argument-type]
        ).run(NCPImportOptions(path=report)),
    )

    assert output.result.documents_ingested == 2  # noqa: PLR2004
    assert output.result.to_console() == "Ingested 2 document(s)."


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
        ) -> PersonTransformationResult:
            assert overwrite is True
            assert created_by == "dietitian"
            if file.filename == "orders.pdf":
                message = "'orders.pdf' is not a PCC progress-note report"
                raise InvalidClinicalNoteReportError(message)
            return PersonTransformationResult(
                documents=[_transformed_document("progress-notes.pdf")],
            )

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

    assert output.result.documents_ingested == 1
    assert len(output.result.failures) == 1
    assert output.result.failures[0].filename == "orders.pdf"
    assert "not a PCC progress-note report" in output.result.failures[0].detail
