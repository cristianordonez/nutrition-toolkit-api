from __future__ import annotations

import argparse
import asyncio
import typing

import pytest

from engine.controllers.ncp import ingest as ingest_module
from engine.controllers.ncp.ingest import (
    NCPIngestController,
    NCPIngestOptions,
)
from engine.pipelines.ncp.ingest.ingest_pipeline import (
    InvalidClinicalNoteReportError,
    NCPIngestSummary,
)

if typing.TYPE_CHECKING:
    import pathlib


class Upload:
    def __init__(self, filename: str) -> None:
        self.filename: str | None = filename

    async def read(self) -> bytes:
        return b"pdf"


def _summary(ingested: int, skipped: int = 0, pointers: int = 0) -> NCPIngestSummary:
    return NCPIngestSummary(
        notes_found=ingested + skipped + pointers,
        notes_ingested=ingested,
        duplicates_skipped=skipped,
        pointer_notes_skipped=pointers,
    )


def test_ingest_command_imports_the_report(
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
        async def run(path: pathlib.Path) -> NCPIngestSummary:
            assert path == report
            return _summary(2, skipped=1, pointers=3)

    monkeypatch.setattr(ingest_module, "NCPIngestPipeline", Pipeline)

    output = asyncio.run(
        NCPIngestController(
            session="session",  # ty: ignore[invalid-argument-type]
        ).run(NCPIngestOptions(path=report)),
    )

    assert output.result.notes_ingested == 2  # noqa: PLR2004
    assert output.result.to_console() == (
        "Ingested 2 NCP example(s) from 1 report(s); skipped 1 duplicate(s) "
        "and 3 pointer note(s)."
    )


def test_ingest_command_rejects_non_pdf(tmp_path: pathlib.Path) -> None:
    report = tmp_path / "progress-notes.txt"
    report.touch()

    with pytest.raises(ValueError, match="is not a PDF"):
        asyncio.run(
            NCPIngestController(
                session="session",  # ty: ignore[invalid-argument-type]
            ).run(NCPIngestOptions(path=report)),
        )


@pytest.mark.parametrize(
    "obsolete_args",
    [["--overwrite"], ["--created-by", "dietitian"]],
)
def test_ingest_command_rejects_removed_options(obsolete_args: list[str]) -> None:
    parser = argparse.ArgumentParser()
    NCPIngestController().add_arguments(parser)

    assert parser.parse_args(["--path", "progress-notes.pdf"]).path.name == (
        "progress-notes.pdf"
    )
    assert "--overwrite" not in parser.format_help()
    assert "--created-by" not in parser.format_help()
    with pytest.raises(SystemExit) as error:
        parser.parse_args(["--path", "progress-notes.pdf", *obsolete_args])
    assert error.value.code == 2  # noqa: PLR2004 - argparse usage error


def test_ingest_single_upload_passes_only_the_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    upload = Upload("progress-notes.pdf")

    class Pipeline:
        @classmethod
        def from_session(cls, session: object) -> Pipeline:
            assert session == "session"
            return cls()

        @staticmethod
        async def run_upload(file: Upload) -> NCPIngestSummary:
            assert file is upload
            return _summary(1)

    monkeypatch.setattr(ingest_module, "NCPIngestPipeline", Pipeline)

    output = asyncio.run(
        NCPIngestController(
            session="session",  # ty: ignore[invalid-argument-type]
        ).run_upload(upload),
    )

    assert output.result.notes_ingested == 1
    assert output.result.failures == []


def test_ingest_uploads_continues_after_invalid_clinical_note_report(
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
        ) -> NCPIngestSummary:
            if file.filename == "orders.pdf":
                message = "'orders.pdf' is not a PCC progress-note report"
                raise InvalidClinicalNoteReportError(message)
            return _summary(1)

    monkeypatch.setattr(ingest_module, "NCPIngestPipeline", Pipeline)

    output = asyncio.run(
        NCPIngestController(
            session="session",  # ty: ignore[invalid-argument-type]
        ).run_uploads(
            [Upload("orders.pdf"), Upload("progress-notes.pdf")],
        ),
    )

    assert output.result.notes_ingested == 1
    assert len(output.result.failures) == 1
    assert output.result.failures[0].filename == "orders.pdf"
    assert "not a PCC progress-note report" in output.result.failures[0].detail
