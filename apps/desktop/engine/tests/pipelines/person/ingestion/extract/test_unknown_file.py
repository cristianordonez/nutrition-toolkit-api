from __future__ import annotations

import asyncio
import typing
from datetime import UTC, date, datetime

import pymupdf
import pytest

from engine.agents.data_extraction_agent import ExtractionInput
from engine.models.ai_extraction import (
    AIExtractedFact,
    AIExtractedIdentity,
    AIUnknownDocumentFact,
)
from engine.models.extracted_fact_create import MealIntakePayload
from engine.pipelines.person.ingestion.extract.unknown_file import (
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
            payload=MealIntakePayload(
                min_percent=50,
                max_percent=75,
                observed_at=datetime(2026, 8, 1, tzinfo=UTC),
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
        "engine.pipelines.person.ingestion.extract.unknown_file.DataExtractionAgent",
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
        "engine.pipelines.person.ingestion.extract.unknown_file.sliding_window",
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


def test_unknown_file_stamps_known_person_id_and_forwards_identity_hints(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "unknown.pdf"
    create_pdf(path)
    extracted = unknown_fact()
    received_inputs: list[ExtractionInput] = []

    async def run_agent(
        extraction_input: ExtractionInput,
    ) -> list[AIUnknownDocumentFact]:
        received_inputs.append(extraction_input)
        return [extracted]

    extractor = UnknownFileExtractor(path)
    monkeypatch.setattr(extractor, "_run_data_extraction_agent", run_agent)
    monkeypatch.setattr(
        "engine.pipelines.person.ingestion.extract.unknown_file.sliding_window",
        lambda text, **_kwargs: [text],
    )

    known_person_id = 42
    facts = asyncio.run(
        extractor.extract(
            person_id=known_person_id,
            known_person_name="Jane Doe",
            known_date_of_birth=date(1950, 1, 1),
        ),
    )

    assert len(facts) == 1
    assert facts[0].person_id == known_person_id
    assert received_inputs[0].known_person_name == "Jane Doe"
    assert received_inputs[0].known_date_of_birth == date(1950, 1, 1)


def test_unknown_file_carries_identity_date_of_birth_onto_fact(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "unknown.pdf"
    create_pdf(path)
    extracted = AIUnknownDocumentFact(
        identity=AIExtractedIdentity(
            source_person_name="Jane Doe",
            date_of_birth=date(1950, 1, 1),
        ),
        fact=unknown_fact().fact,
    )
    extractor = UnknownFileExtractor(path)
    monkeypatch.setattr(
        extractor,
        "_run_data_extraction_agent",
        lambda _input: _async_result([extracted]),
    )
    monkeypatch.setattr(
        "engine.pipelines.person.ingestion.extract.unknown_file.sliding_window",
        lambda text, **_kwargs: [text],
    )

    facts = asyncio.run(extractor.extract())

    assert facts[0].date_of_birth == date(1950, 1, 1)
    assert facts[0].person_id is None


def test_unknown_file_isolates_one_chunk_failure_and_continues(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A chunk whose extraction raises (e.g. an invalid-datetime validation

    error from the model) must not abort extraction of the rest of the
    document; the other pages should still return their facts.
    """
    path = tmp_path / "unknown.pdf"
    create_pdf(path)
    extracted = unknown_fact()
    call_count = 0

    async def run_agent(
        _extraction_input: ExtractionInput,
    ) -> list[AIUnknownDocumentFact]:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            message = (
                "1 validation error for MealIntakePayload\n"
                "observed_at\n  Input should be a valid datetime"
            )
            raise ValueError(message)
        return [extracted]

    extractor = UnknownFileExtractor(path)
    monkeypatch.setattr(extractor, "_run_data_extraction_agent", run_agent)
    monkeypatch.setattr(
        extractor,
        "_get_document_pages",
        lambda: [(1, "page one text"), (2, "page two text")],
    )
    monkeypatch.setattr(
        "engine.pipelines.person.ingestion.extract.unknown_file.sliding_window",
        lambda text, **_kwargs: [text],
    )

    facts = asyncio.run(extractor.extract())

    assert call_count == 2  # noqa: PLR2004
    assert len(facts) == 1
    assert facts[0].source_page == 2  # noqa: PLR2004


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "Filed: 9/14/2026 15:15",
            datetime(2026, 9, 14, 15, 15, tzinfo=UTC),
        ),
        (
            "Date of Service: 8/26/2026",
            datetime(2026, 8, 26, 0, 0, tzinfo=UTC),
        ),
        (
            "Result Date: 09/07/26",
            datetime(2026, 9, 7, 0, 0, tzinfo=UTC),
        ),
        (
            "No dated label present in this text at all.",
            None,
        ),
    ],
)
def test_detect_note_date(text: str, expected: datetime | None) -> None:
    assert UnknownFileExtractor._detect_note_date(text) == expected  # noqa: SLF001


async def _async_result(
    value: list[AIUnknownDocumentFact],
) -> list[AIUnknownDocumentFact]:
    return value
