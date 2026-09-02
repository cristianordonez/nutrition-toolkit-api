from __future__ import annotations

import asyncio
import typing

from ntk.controllers.documents import ingest
from ntk.controllers.documents.ingest import (
    DocumentIngestController,
    DocumentIngestOptions,
)
from ntk.services.resident_data.transform import ResidentTransformationResult

if typing.TYPE_CHECKING:
    import pathlib

    import pytest


class Upload:
    filename = "document.txt"
    content = b"resident report"

    async def read(self) -> bytes:
        return self.content


def test_document_ingest_accepts_multiple_uploads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed_paths: list[pathlib.Path] = []

    class Service:
        async def ingest(
            self,
            files: list[pathlib.Path],
        ) -> ResidentTransformationResult:
            observed_paths.extend(files)
            assert all(path.is_file() for path in files)
            return ResidentTransformationResult(documents=[])

    monkeypatch.setattr(ingest, "ProgressNoteRepo", lambda session: session)
    monkeypatch.setattr(ingest, "ResidentRepo", lambda session: session)
    monkeypatch.setattr(ingest, "ResidentIngestionService", lambda **_: Service())
    controller = DocumentIngestController(session=object())  # ty: ignore[invalid-argument-type]
    first_upload = Upload()
    first_upload.filename = "first.txt"
    second_upload = Upload()
    second_upload.filename = "second.txt"
    second_upload.content = b"second resident report"

    output = asyncio.run(
        controller.run(DocumentIngestOptions(files=[first_upload, second_upload])),
    )

    assert len(observed_paths) == 2  # noqa: PLR2004
    assert output.controller == "ingest"
    assert output.result.documents == []
    assert all(not path.exists() for path in observed_paths)


def test_document_ingest_uses_configured_parallel_pool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed_configuration: list[tuple[object, int]] = []

    class Handler:
        def __init__(self, *, mode: object, workers: int) -> None:
            observed_configuration.append((mode, workers))

        @staticmethod
        def map(
            function: typing.Callable[[pathlib.Path], ResidentTransformationResult],
            paths: list[pathlib.Path],
        ) -> list[ResidentTransformationResult]:
            return [function(path) for path in paths]

    def ingest_one(path: pathlib.Path) -> ResidentTransformationResult:
        assert path.is_file()
        return ResidentTransformationResult(documents=[])

    monkeypatch.setattr(ingest, "ParallelPoolHandler", Handler)
    monkeypatch.setattr(ingest, "_ingest_document", ingest_one)
    first_upload = Upload()
    first_upload.filename = "first.txt"
    second_upload = Upload()
    second_upload.filename = "second.txt"
    second_upload.content = b"second resident report"

    output = asyncio.run(
        DocumentIngestController().run(
            DocumentIngestOptions(files=[first_upload, second_upload]),
        ),
    )

    assert observed_configuration == [
        (
            ingest.SETTINGS.document_ingestion_pool_mode,
            ingest.SETTINGS.document_ingestion_workers,
        ),
    ]
    assert output.result.documents == []
