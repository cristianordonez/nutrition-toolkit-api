from __future__ import annotations

import asyncio
import typing
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from ntk.models.document import Document, StoredDocumentType
from ntk.presentation.api.routers import rag


class FakeOpenAIService:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def create_embedding(self, content: str) -> list[float]:
        self.queries.append(content)
        return [0.1, 0.2]


class FakeCursor:
    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self.rows = rows
        self.query = ""
        self.parameters: tuple[object, ...] = ()

    def __enter__(self) -> typing.Self:
        return self

    def __exit__(self, *args: object) -> None:
        del args

    def execute(self, query: str, parameters: tuple[object, ...]) -> None:
        self.query = query
        self.parameters = parameters

    def fetchall(self) -> list[tuple[object, ...]]:
        return self.rows


class FakeConnection:
    def __init__(self, cursor: FakeCursor) -> None:
        self._cursor = cursor

    def __enter__(self) -> typing.Self:
        return self

    def __exit__(self, *args: object) -> None:
        del args

    def cursor(self) -> FakeCursor:
        return self._cursor


def test_search_embeds_query_and_clamps_top_k(monkeypatch: pytest.MonkeyPatch) -> None:
    document_id = uuid4()
    cursor = FakeCursor(
        [(document_id, "manual.pdf", "Clinical guidance", 0.87)],
    )
    service = FakeOpenAIService()
    monkeypatch.setattr(rag, "_OPEN_AI_SERVICE", service)
    monkeypatch.setattr(rag, "_connect", lambda: FakeConnection(cursor))

    matches = rag.search_documents("  protein needs  ", 100)

    assert service.queries == ["protein needs"]
    assert cursor.parameters == (
        "[0.1,0.2]",
        "nutrition-care-manual",
        "[0.1,0.2]",
        20,
    )
    assert "embedding_vector <=> %s::vector" in cursor.query
    assert "WHERE d.document_type = %s" in cursor.query
    assert matches[0].document_id == document_id
    assert matches[0].filename == "manual.pdf"
    assert matches[0].chunk_text == "Clinical guidance"
    assert matches[0].similarity == pytest.approx(0.87)


def test_search_returns_empty_list_when_no_embeddings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cursor = FakeCursor([])
    monkeypatch.setattr(rag, "_OPEN_AI_SERVICE", FakeOpenAIService())
    monkeypatch.setattr(rag, "_connect", lambda: FakeConnection(cursor))

    assert rag.search_documents("nutrition", 0) == []
    assert cursor.parameters[-1] == 1


def test_search_rejects_blank_text() -> None:
    with pytest.raises(HTTPException, match="must not be empty") as exc_info:
        rag.search_documents("   ", 5)

    assert exc_info.value.status_code == 422  # noqa: PLR2004


class FakeUpload:
    def __init__(self, filename: str | None, content: bytes = b"content") -> None:
        self.filename = filename
        self.content = content

    async def read(self) -> bytes:
        return self.content


def test_ingest_pdfs_writes_uploads_and_restores_filenames(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Controller:
        def run(self, _: object) -> object:
            documents = [
                Document(
                    filename="temporary.pdf",
                    document_type=StoredDocumentType.ASSESSMENT,
                    file_hash="hash",
                ),
            ]
            return SimpleNamespace(result=rag.IngestResponse(documents=documents))

    monkeypatch.setattr(rag, "IngestController", Controller)
    upload = FakeUpload("assessment.pdf")

    response = asyncio.run(
        rag.ingest_pdfs(  # ty: ignore[invalid-argument-type]
            [upload],
            StoredDocumentType.ASSESSMENT,
            overwrite=True,
        ),
    )

    assert response.documents[0].filename == "assessment.pdf"


def test_ingest_pdfs_rejects_empty_and_unsupported_uploads() -> None:
    with pytest.raises(HTTPException, match="At least one"):
        asyncio.run(rag.ingest_pdfs([], StoredDocumentType.ASSESSMENT))

    with pytest.raises(HTTPException, match="not a PDF or text file"):
        asyncio.run(
            rag.ingest_pdfs(  # ty: ignore[invalid-argument-type]
                [FakeUpload("assessment.csv")],
                StoredDocumentType.ASSESSMENT,
            ),
        )
