"""Tests for the knowledge extractor contract and ingestion pipeline."""

from __future__ import annotations

import asyncio
import typing

from api.models.knowledge import (
    ExtractedKnowledgePage,
    KnowledgeChunkCreate,
    KnowledgeType,
)
from api.pipelines.knowledge.ingestion import pipeline as knowledge_pipeline
from api.pipelines.knowledge.ingestion import processing as knowledge_processing
from api.pipelines.knowledge.ingestion.extractors.base import KnowledgeExtractor
from api.pipelines.knowledge.ingestion.extractors.knowledge_extractor import (
    DietManualExtractor,
)
from api.pipelines.knowledge.ingestion.pipeline import KnowledgeIngestionPipeline
from ntk.pipelines.extraction import DocumentExtractor

if typing.TYPE_CHECKING:
    import pathlib

    from api.models.sql.knowledge import Knowledge


def test_knowledge_extractor_is_a_document_extractor() -> None:
    assert issubclass(KnowledgeExtractor, DocumentExtractor)


def test_knowledge_extractor_preserves_pages(tmp_path: pathlib.Path) -> None:
    import pymupdf

    source = tmp_path / "diet-manual.pdf"
    with pymupdf.open() as document:
        for text in (
            "Diet Manual\nUse individualized nutrition interventions.",
            "Second page guidance.",
        ):
            page = document.new_page()
            page.insert_text((20, 40), text)
        document.save(source)
    extractor = DietManualExtractor(source)

    pages = asyncio.run(extractor.extract())

    assert [page.page_number for page in pages] == [1, 2]
    assert pages[0].text == ("Diet Manual\nUse individualized nutrition interventions.")
    assert extractor.create_knowledge().filename == source.name


def test_knowledge_pipeline_persists_plain_extracted_chunks(
    tmp_path: pathlib.Path,
    monkeypatch,  # noqa: ANN001
) -> None:
    source = tmp_path / "diet-manual.pdf"
    source.write_bytes(b"manual")

    class StubExtractor(KnowledgeExtractor):
        knowledge_type = KnowledgeType.DIET_MANUAL

        def is_expected_format(self) -> bool:
            return True

        async def extract(self) -> list[ExtractedKnowledgePage]:
            return [
                ExtractedKnowledgePage(
                    page_number=7,
                    text="first chunk\nsecond chunk",
                ),
            ]

    class Repository:
        def __init__(self) -> None:
            self.chunks: list[str] = []

        @staticmethod
        def find_existing_knowledge(
            _knowledge_type: KnowledgeType,
            _file_hash: str,
        ) -> None:
            return None

        def ingest(
            self,
            knowledge: Knowledge,
            chunks: list[KnowledgeChunkCreate],
            embeddings: list[list[float]],
            model_name: str,
            *,
            overwrite: bool,
        ) -> Knowledge:
            assert embeddings == [[1.0], [2.0]]
            assert model_name == "test-embedding"
            assert overwrite is True
            self.chunks = [chunk.content for chunk in chunks]
            return knowledge

    class Embeddings:
        embedding_model = "test-embedding"

        @staticmethod
        async def get_embeddings_async(chunks: list[str]) -> list[list[float]]:
            assert chunks == ["first chunk", "second chunk"]
            return [[1.0], [2.0]]

    repository = Repository()
    monkeypatch.setattr(
        knowledge_pipeline,
        "_EXTRACTORS_BY_TYPE",
        {KnowledgeType.DIET_MANUAL: StubExtractor},
    )
    monkeypatch.setattr(
        knowledge_processing,
        "sliding_window",
        lambda text: text.splitlines(),
    )
    pipeline = KnowledgeIngestionPipeline(
        typing.cast("typing.Any", repository),
        typing.cast("typing.Any", Embeddings()),
    )

    result = asyncio.run(
        pipeline.ingest_knowledge(
            source,
            KnowledgeType.DIET_MANUAL,
            overwrite=True,
        ),
    )

    assert result.filename == source.name
    assert repository.chunks == ["first chunk", "second chunk"]
