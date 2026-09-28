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
    # The document's identifier belongs to another system, so it is dropped;
    # the resident is matched by name and date of birth.
    assert facts[0].source_person_identifier is None
    assert facts[0].source_person_name == "Jane Doe"
    assert facts[0].person_id is None
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


def _fact_on(day: int) -> AIUnknownDocumentFact:
    fact = unknown_fact()
    fact.fact.payload.observed_at = datetime(2026, 8, day, tzinfo=UTC)  # ty: ignore[invalid-assignment]
    return fact


def test_each_page_is_one_call_run_concurrently_and_kept_in_order(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "unknown.pdf"
    create_pdf(path)
    pages = [(page, f"page {page} text") for page in range(1, 7)]
    in_flight = 0
    peak = 0
    seen: list[str] = []

    async def run_agent(
        extraction_input: ExtractionInput,
    ) -> list[AIUnknownDocumentFact]:
        nonlocal in_flight, peak
        seen.append(extraction_input.text)
        in_flight += 1
        peak = max(peak, in_flight)
        page = int(extraction_input.text.split()[1])
        # Later pages finish first, so order must come from the page, not
        # from completion.
        await asyncio.sleep(0.01 * (7 - page))
        in_flight -= 1
        return [_fact_on(page)]

    extractor = UnknownFileExtractor(path, concurrency=3)
    monkeypatch.setattr(extractor, "_run_data_extraction_agent", run_agent)
    monkeypatch.setattr(extractor, "_get_document_pages", lambda: pages)

    facts = asyncio.run(extractor.extract())

    assert sorted(seen) == [text for _, text in pages]
    assert peak == 3  # noqa: PLR2004
    assert [fact.source_page for fact in facts] == [1, 2, 3, 4, 5, 6]


def test_only_an_oversized_page_is_split(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "unknown.pdf"
    create_pdf(path)
    pages_sent: list[str] = []
    ordinary = "Weight 150 lb. " * 200  # well under one call's budget
    huge = "Albumin 3.1 g/dL. " * 3_000  # far over it

    async def run_agent(
        extraction_input: ExtractionInput,
    ) -> list[AIUnknownDocumentFact]:
        pages_sent.append(
            "ordinary" if extraction_input.text.startswith("Weight") else "huge",
        )
        return []

    extractor = UnknownFileExtractor(path)
    monkeypatch.setattr(extractor, "_run_data_extraction_agent", run_agent)
    monkeypatch.setattr(
        extractor,
        "_get_document_pages",
        lambda: [(1, ordinary), (2, huge)],
    )

    asyncio.run(extractor.extract())

    assert pages_sent.count("ordinary") == 1
    assert pages_sent.count("huge") > 1


def test_concurrency_must_be_positive(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "unknown.pdf"
    create_pdf(path)

    with pytest.raises(ValueError, match="at least 1"):
        UnknownFileExtractor(path, concurrency=0)


def test_an_outside_identifier_never_blocks_attribution(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two systems' MRNs for one patient must not read as two people."""
    path = tmp_path / "hospital-packet.pdf"
    create_pdf(path)

    def fact_with(identifier: str | None, *, named: bool) -> AIUnknownDocumentFact:
        return AIUnknownDocumentFact(
            identity=AIExtractedIdentity(
                source_person_name="Jane Doe" if named else None,
                source_person_identifier=identifier,
                date_of_birth=date(1950, 1, 1) if named else None,
            ),
            fact=unknown_fact().fact,
        )

    by_page = {
        1: [fact_with("H-0001", named=True)],
        2: [fact_with("ACCT-77", named=True)],
        3: [fact_with(None, named=False)],
    }

    async def run_agent(
        extraction_input: ExtractionInput,
    ) -> list[AIUnknownDocumentFact]:
        return by_page[int(extraction_input.text)]

    extractor = UnknownFileExtractor(path)
    monkeypatch.setattr(extractor, "_run_data_extraction_agent", run_agent)
    monkeypatch.setattr(
        extractor,
        "_get_document_pages",
        lambda: [(page, str(page)) for page in by_page],
    )

    facts = asyncio.run(extractor.extract())

    assert [fact.source_person_identifier for fact in facts] == [None, None, None]
    assert all(fact.source_person_name == "Jane Doe" for fact in facts)
    assert all(fact.date_of_birth == date(1950, 1, 1) for fact in facts)
