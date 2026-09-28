"""Wire the structure-aware processor into the knowledge ingestion pipeline."""

from __future__ import annotations

import asyncio
import typing
from unittest.mock import AsyncMock, Mock

import pytest

from engine.database.vectors import EMBEDDING_DIMENSIONS
from engine.models.knowledge import ExtractedKnowledgePage, KnowledgeChunkCreate
from engine.models.sql.knowledge import Knowledge, KnowledgeType
from engine.pipelines.knowledge.ingestion import pipeline as ingestion
from engine.pipelines.knowledge.ingestion.processing import (
    KnowledgeContentProcessor,
)
from engine.pipelines.knowledge.ingestion.processing.processing import (
    KnowledgeContentProcessor as ProcessorImplementation,
)
from engine.repositories.knowledge_repo import KnowledgeRepo
from engine.services.embedding_service import EmbeddingService

if typing.TYPE_CHECKING:
    import pathlib

_FIRST_PAGE = 5
_LAST_PAGE = 6
pytestmark = pytest.mark.usefixtures("embedding_tokenizer")


@pytest.fixture
def pipeline(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> ingestion.KnowledgeIngestionPipeline:
    (tmp_path / "manual.pdf").touch()
    knowledge = Knowledge(
        filename="manual.pdf",
        knowledge_type=KnowledgeType.NUTRITION_CARE_MANUAL,
        file_hash="manual-content",
    )
    extractor = Mock()
    extractor.is_expected_format.return_value = True
    extractor.create_knowledge.return_value = knowledge
    extractor.extract = AsyncMock(
        return_value=[
            ExtractedKnowledgePage(
                page_number=_FIRST_PAGE,
                text=(
                    "Diabetes Mellitus > Type 2 Diabetes\n"
                    "Nutrition Assessment\n"
                    "Review food intake and meal timing."
                ),
            ),
            ExtractedKnowledgePage(
                page_number=_LAST_PAGE,
                text=(
                    "Consider the person's usual eating pattern.\n"
                    "References\n"
                    "A citation that must not be embedded."
                ),
            ),
        ],
    )
    monkeypatch.setitem(
        ingestion._EXTRACTORS_BY_TYPE,  # noqa: SLF001 - replace document I/O
        KnowledgeType.NUTRITION_CARE_MANUAL,
        Mock(return_value=extractor),
    )
    repository = Mock(spec=KnowledgeRepo)
    repository.find_existing_knowledge.return_value = None
    repository.ingest.return_value = knowledge
    embedder = Mock(spec=EmbeddingService)
    embedder.get_embeddings_async.return_value = [[1.0] * EMBEDDING_DIMENSIONS]
    return ingestion.KnowledgeIngestionPipeline(repository, embedder)


def test_pipeline_uses_new_processor_and_preserves_chunk_context(
    pipeline: ingestion.KnowledgeIngestionPipeline,
    tmp_path: pathlib.Path,
) -> None:
    assert KnowledgeContentProcessor is ProcessorImplementation
    assert isinstance(pipeline.content_processor, ProcessorImplementation)

    result = asyncio.run(
        pipeline.ingest_knowledge(
            tmp_path / "manual.pdf",
            KnowledgeType.NUTRITION_CARE_MANUAL,
        ),
    )

    repository = typing.cast("Mock", pipeline.knowledge_repository)
    embedder = typing.cast("Mock", pipeline.embedding_service)
    knowledge, chunks, vectors = repository.ingest.call_args.args
    assert result is knowledge
    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.section_title == "Nutrition Assessment"
    assert chunk.section_path == (
        "Diabetes Mellitus > Type 2 Diabetes > Nutrition Assessment"
    )
    assert chunk.content.startswith(chunk.section_path + "\n\n")
    assert "Review food intake" in chunk.content
    assert "usual eating pattern" in chunk.content
    assert "citation" not in chunk.content
    assert chunk.source_page_start == _FIRST_PAGE
    assert chunk.source_page_end == _LAST_PAGE
    embedder.get_embeddings_async.assert_awaited_once_with([chunk.content])
    assert vectors is embedder.get_embeddings_async.return_value
    assert repository.ingest.call_args.kwargs == {"overwrite": False}


def test_pipeline_still_accepts_an_injected_processor(
    pipeline: ingestion.KnowledgeIngestionPipeline,
    tmp_path: pathlib.Path,
) -> None:
    processor = Mock(spec=KnowledgeContentProcessor)
    processor.build_chunks.return_value = [
        KnowledgeChunkCreate(
            content="Custom processed content",
            source_page_start=_FIRST_PAGE,
            source_page_end=_LAST_PAGE,
        ),
    ]
    custom_pipeline = ingestion.KnowledgeIngestionPipeline(
        pipeline.knowledge_repository,
        pipeline.embedding_service,
        processor,
    )

    asyncio.run(
        custom_pipeline.ingest_knowledge(
            tmp_path / "manual.pdf",
            KnowledgeType.NUTRITION_CARE_MANUAL,
        ),
    )

    processor.build_chunks.assert_called_once()
    assert [page.page_number for page in processor.build_chunks.call_args.args[0]] == [
        _FIRST_PAGE,
        _LAST_PAGE,
    ]
    embedder = typing.cast("Mock", pipeline.embedding_service)
    embedder.get_embeddings_async.assert_awaited_once_with(["Custom processed content"])


@pytest.mark.parametrize("overwrite", [False, True])
def test_existing_manual_preserves_overwrite_behavior(
    pipeline: ingestion.KnowledgeIngestionPipeline,
    tmp_path: pathlib.Path,
    *,
    overwrite: bool,
) -> None:
    repository = typing.cast("Mock", pipeline.knowledge_repository)
    embedder = typing.cast("Mock", pipeline.embedding_service)
    existing = repository.ingest.return_value
    repository.find_existing_knowledge.return_value = existing

    result = asyncio.run(
        pipeline.ingest_knowledge(
            tmp_path / "manual.pdf",
            KnowledgeType.NUTRITION_CARE_MANUAL,
            overwrite=overwrite,
        ),
    )

    assert result is existing
    if overwrite:
        repository.ingest.assert_called_once()
        assert repository.ingest.call_args.kwargs == {"overwrite": True}
        embedder.get_embeddings_async.assert_awaited_once()
    else:
        repository.ingest.assert_not_called()
        embedder.get_embeddings_async.assert_not_awaited()
