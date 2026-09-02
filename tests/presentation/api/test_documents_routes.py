from __future__ import annotations

import asyncio
import typing
from types import SimpleNamespace

from ntk.presentation.api.routers import documents
from ntk.services.resident_data.transform import ResidentTransformationResult

if typing.TYPE_CHECKING:
    import pytest

    from ntk.controllers.documents.ingest import DocumentIngestOptions

_UPLOAD_COUNT = 2


class Upload:
    filename = "document.pdf"

    async def read(self) -> bytes:
        return b"pdf"


def test_ingestion_route_calls_document_controller(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = ResidentTransformationResult(documents=[])

    class Controller:
        async def run(self, options: DocumentIngestOptions) -> object:
            assert len(options.files) == _UPLOAD_COUNT
            return SimpleNamespace(result=expected)

    monkeypatch.setattr(documents, "DocumentIngestController", Controller)

    result = asyncio.run(
        documents.ingest_documents(
            [Upload(), Upload()],  # ty: ignore[invalid-argument-type]
        ),
    )

    assert result is expected
