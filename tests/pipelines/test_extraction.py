"""Tests for the shared extraction contract and domain extractors."""

from __future__ import annotations

import asyncio
import inspect
import typing
from datetime import UTC, datetime

import pymupdf
import pytest

from ntk.models.extracted_fact_create import ExtractedFactCreate, WeightPayload
from ntk.models.knowledge import (
    ExtractedKnowledgePage,
    KnowledgeChunkCreate,
    KnowledgeType,
)
from ntk.pipelines.extraction import DocumentExtractor
from ntk.pipelines.knowledge.ingestion import pipeline as knowledge_pipeline
from ntk.pipelines.knowledge.ingestion import processing as knowledge_processing
from ntk.pipelines.knowledge.ingestion.extractors import registry as knowledge_registry
from ntk.pipelines.knowledge.ingestion.extractors.base import KnowledgeExtractor
from ntk.pipelines.knowledge.ingestion.extractors.knowledge_extractor import (
    DietManualExtractor,
)
from ntk.pipelines.knowledge.ingestion.pipeline import KnowledgeIngestionPipeline
from ntk.pipelines.person.ingestion.extract import registry as person_registry
from ntk.pipelines.person.ingestion.extract.base import PersonExtractor

if typing.TYPE_CHECKING:
    import pathlib

    from ntk.models.sql.knowledge import Knowledge


class TextExtractor(DocumentExtractor[str]):
    """Concrete shared extractor used to exercise document mechanics."""

    def is_expected_format(self) -> bool:
        return self._is_pdf(self.path)

    async def extract(self) -> str:
        return self._document_text


class FactExtractor(PersonExtractor):
    """Concrete person extractor used to exercise fact construction."""

    def is_expected_format(self) -> bool:
        return True

    async def extract(self) -> list[ExtractedFactCreate]:
        return []


def _write_pdf(path: pathlib.Path, *pages: str) -> None:
    with pymupdf.open() as document:
        for text in pages:
            page = document.new_page()
            page.insert_text((20, 40), text)
        document.save(path)


def test_document_extractor_is_generic_abstract_contract() -> None:
    assert inspect.isabstract(DocumentExtractor)
    assert issubclass(PersonExtractor, DocumentExtractor)
    assert issubclass(KnowledgeExtractor, DocumentExtractor)
    assert PersonExtractor is not KnowledgeExtractor


def test_shared_document_helpers_and_generic_extract(
    tmp_path: pathlib.Path,
) -> None:
    source = tmp_path / "manual.PDF"
    _write_pdf(source, "Diet Manual", "Nutrition guidance")
    extractor = TextExtractor(source)

    assert DocumentExtractor._is_pdf(source)  # noqa: SLF001
    assert extractor._first_page_contains("diet manual")  # noqa: SLF001
    assert extractor._first_page_text == "Diet Manual"  # noqa: SLF001
    assert asyncio.run(extractor.extract()) == "Diet Manual\nNutrition guidance"


def test_shared_document_text_rejects_unrecognized_format(
    tmp_path: pathlib.Path,
) -> None:
    source = tmp_path / "manual.txt"
    source.write_text("Diet Manual")

    with pytest.raises(TypeError, match="unsupported file format"):
        asyncio.run(TextExtractor(source).extract())


def test_person_extractor_builds_facts_and_parses_facility(
    tmp_path: pathlib.Path,
) -> None:
    extractor = FactExtractor(tmp_path / "weights.pdf")
    fact = extractor._build_extracted_fact(  # noqa: SLF001
        WeightPayload(
            weight_lb=150,
            measured_at=datetime(2026, 9, 1, tzinfo=UTC),
        ),
        source_person_identifier="A123",
        facility_name="Embassy Manor",
    )

    assert fact.source_person_identifier == "A123"
    assert fact.facility_name == "Embassy Manor"
    assert fact.confidence == 1.0
    assert (
        PersonExtractor._parse_facility_name(  # noqa: SLF001
            "Weights and Vitals Summary\nEmbassy Manor\nResident: Example",
            "Weights and Vitals Summary",
        )
        == "Embassy Manor"
    )
    assert not hasattr(KnowledgeExtractor, "_build_extracted_fact")
    assert not hasattr(DocumentExtractor, "_parse_facility_name")


def test_knowledge_extractor_preserves_pages(tmp_path: pathlib.Path) -> None:
    source = tmp_path / "diet-manual.pdf"
    _write_pdf(
        source,
        "Diet Manual\nUse individualized nutrition interventions.",
        "Second page guidance.",
    )
    extractor = DietManualExtractor(source)

    pages = asyncio.run(extractor.extract())

    assert [page.page_number for page in pages] == [1, 2]
    assert pages[0].text == ("Diet Manual\nUse individualized nutrition interventions.")
    assert extractor.create_knowledge().filename == source.name


def test_person_and_knowledge_registries_are_independent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(person_registry, "EXTRACTOR_REGISTRY", {})
    monkeypatch.setattr(knowledge_registry, "EXTRACTOR_REGISTRY", {})

    @person_registry.register_extractor
    class RegisteredPersonExtractor(FactExtractor):
        pass

    @knowledge_registry.register_extractor
    class RegisteredKnowledgeExtractor(KnowledgeExtractor):
        knowledge_type = DietManualExtractor.knowledge_type

        def is_expected_format(self) -> bool:
            return True

    assert {
        "RegisteredPersonExtractor": RegisteredPersonExtractor,
    } == person_registry.EXTRACTOR_REGISTRY
    assert {
        "RegisteredKnowledgeExtractor": RegisteredKnowledgeExtractor,
    } == knowledge_registry.EXTRACTOR_REGISTRY
    with pytest.raises(TypeError, match="must inherit from KnowledgeExtractor"):
        knowledge_registry.register_extractor(
            RegisteredPersonExtractor,  # ty: ignore[invalid-argument-type]
        )


def test_knowledge_pipeline_persists_plain_extracted_chunks(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
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
