from __future__ import annotations

import asyncio
import typing
from datetime import UTC, datetime

import pymupdf
import pytest

from ntk.agents.data_extraction_agent import ExtractionInput
from ntk.models.ai_extraction import (
    AIExtractedFact,
    AIExtractedIdentity,
    AIUnknownDocumentFact,
)
from ntk.models.extracted_fact_create import WeightPayload
from ntk.pipelines.person.ingestion.extract.unknown_file import (
    UnknownFileExtractor,
    UnknownFileTooLargeError,
)

if typing.TYPE_CHECKING:
    import pathlib


def create_pdf(path: pathlib.Path, text: str = "Person weight: 140 lb") -> None:
    with pymupdf.open() as document:
        page = document.new_page()
        page.insert_text((20, 40), text, fontsize=8)
        document.save(path)


def unknown_fact() -> AIUnknownDocumentFact:
    return AIUnknownDocumentFact(
        identity=AIExtractedIdentity(
            source_person_name="Jane Doe",
            source_person_identifier="RES-1",
            facility_name="Sunrise Care",
        ),
        fact=AIExtractedFact(
            payload=WeightPayload(
                weight_lb=140,
                measured_at=datetime(2026, 8, 1, tzinfo=UTC),
            ),
            confidence=0.95,
        ),
    )


def test_unknown_file_uses_unknown_document_agent_method(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "unknown.pdf"
    create_pdf(path)
    extraction_input = ExtractionInput(text="Person weight: 140 lb")
    expected = [unknown_fact()]

    class Agent:
        @staticmethod
        async def run(_input: ExtractionInput) -> typing.Never:
            message = "generic run method should not be used"
            raise AssertionError(message)

        @staticmethod
        async def run_unknown_document(
            received: ExtractionInput,
        ) -> list[AIUnknownDocumentFact]:
            assert received is extraction_input
            return expected

    monkeypatch.setattr(
        "ntk.pipelines.person.ingestion.extract.unknown_file.DataExtractionAgent",
        Agent,
    )
    extractor = UnknownFileExtractor(path)

    result = asyncio.run(
        extractor._run_data_extraction_agent(extraction_input),  # noqa: SLF001
    )
    assert result == expected


def test_unknown_file_returns_unresolved_identity_clues(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "unknown.pdf"
    create_pdf(path)
    extracted = unknown_fact()
    extractor = UnknownFileExtractor(path)
    monkeypatch.setattr(
        extractor,
        "_run_data_extraction_agent",
        lambda _input: _async_result([extracted]),
    )
    monkeypatch.setattr(
        "ntk.pipelines.person.ingestion.extract.unknown_file.sliding_window",
        lambda text, **_kwargs: [text],
    )

    facts = asyncio.run(extractor.extract())

    assert len(facts) == 1
    assert facts[0].source_person_identifier == "RES-1"
    assert facts[0].source_person_name == "Jane Doe"
    assert facts[0].facility_name == "Sunrise Care"
    assert facts[0].person_id is None
    assert facts[0].facility_id is None
    assert facts[0].source_page == 1


def test_unknown_file_rejects_oversized_file(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "large.pdf"
    path.write_bytes(b"too large")

    with pytest.raises(UnknownFileTooLargeError, match=r"large\.pdf.*maximum size"):
        UnknownFileExtractor(path, max_file_size_bytes=4)


async def _async_result(
    value: list[AIUnknownDocumentFact],
) -> list[AIUnknownDocumentFact]:
    return value
