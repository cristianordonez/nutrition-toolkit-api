from __future__ import annotations

import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from ntk.controllers.knowledge.search import (
    KnowledgeSearchResponse,
)
from ntk.models.knowledge import KnowledgeIngestResponsePublic, KnowledgeType
from ntk.models.rag import RagSearchMatch
from ntk.models.sql.knowledge import Knowledge, KnowledgeChunk
from ntk.presentation.api.routers import knowledge as rag


def test_search_uses_controller_and_clamps_top_k(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document_id = uuid4()
    match = RagSearchMatch(
        document_id=document_id,
        filename="manual.pdf",
        chunk_text="Clinical guidance",
        similarity=0.87,
    )

    class Controller:
        def search(self, text: str, top_k: int) -> object:
            assert text == "  protein needs  "
            assert top_k == 100  # noqa: PLR2004
            return SimpleNamespace(result=KnowledgeSearchResponse(matches=[match]))

    monkeypatch.setattr(rag, "_KNOWLEDGE_SEARCH_CONTROLLER", Controller())

    matches = asyncio.run(rag.search_documents("  protein needs  ", 100))

    assert matches[0].document_id == document_id
    assert matches[0].filename == "manual.pdf"
    assert matches[0].chunk_text == "Clinical guidance"
    assert matches[0].similarity == pytest.approx(0.87)


def test_search_returns_controller_matches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Controller:
        def search(self, text: str, top_k: int) -> object:
            assert text == "nutrition"
            assert top_k == 0
            return SimpleNamespace(result=KnowledgeSearchResponse(matches=[]))

    monkeypatch.setattr(rag, "_KNOWLEDGE_SEARCH_CONTROLLER", Controller())

    assert asyncio.run(rag.search_documents("nutrition", 0)) == []


def test_search_rejects_blank_text() -> None:
    with pytest.raises(HTTPException, match="must not be empty") as exc_info:
        asyncio.run(rag.search_documents("   ", 5))

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
        async def run_uploads(
            self,
            files: list[FakeUpload],
            document_type: KnowledgeType,
            *,
            overwrite: bool,
        ) -> object:
            assert files[0].filename == "assessment.pdf"
            assert document_type is KnowledgeType.NUTRITION_CARE_MANUAL
            assert overwrite is True
            knowledge = Knowledge(
                filename="assessment.pdf",
                knowledge_type=KnowledgeType.NUTRITION_CARE_MANUAL,
                file_hash="hash",
            )
            knowledge.chunks.append(
                KnowledgeChunk(
                    knowledge_id=knowledge.id,
                    chunk_index=0,
                    content="Clinical guidance",
                ),
            )
            return SimpleNamespace(
                result=KnowledgeIngestResponsePublic.from_documents([knowledge]),
            )

    monkeypatch.setattr(rag, "_KNOWLEDGE_INGEST_CONTROLLER", Controller())
    upload = FakeUpload("assessment.pdf")

    response = asyncio.run(
        rag.ingest_pdfs(
            [upload],  # ty: ignore[invalid-argument-type]
            KnowledgeType.NUTRITION_CARE_MANUAL,
            overwrite=True,
        ),
    )

    assert response.documents[0].filename == "assessment.pdf"
    assert response.chunk_count == 1
    assert response.model_dump()["chunk_count"] == 1
    assert response.documents[0].chunks[0].content == "Clinical guidance"


def test_ingest_pdfs_rejects_empty_and_unsupported_uploads() -> None:
    with pytest.raises(HTTPException, match="At least one"):
        asyncio.run(
            rag.ingest_pdfs([], KnowledgeType.NUTRITION_CARE_MANUAL),
        )

    with pytest.raises(HTTPException, match="not a PDF or text file"):
        asyncio.run(
            rag.ingest_pdfs(
                [FakeUpload("assessment.csv")],  # ty: ignore[invalid-argument-type]
                KnowledgeType.NUTRITION_CARE_MANUAL,
            ),
        )
