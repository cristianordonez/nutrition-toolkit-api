from __future__ import annotations

import asyncio
import logging
import typing
from datetime import UTC, date, datetime

import pytest

from ntk.agents.data_extraction_agent import ExtractedClinicalFacts, ExtractionInput
from ntk.models.ai_extraction import AIExtractedClinicalFact
from ntk.models.extracted_fact_create import ClinicalFactPayload, WoundPayload
from ntk.models.sql.resident import ExtractionStatus, ResidentProgressNote
from ntk.services.resident_data.extract.pcc_progress_notes import (
    ExtractedNote,
    ParsedProgressNote,
    PccProgressNotesExtractor,
    ProgressNoteAction,
    clean_note_text,
)
from ntk.services.resident_data.resident_resolver import ResidentResolution

if typing.TYPE_CHECKING:
    import pathlib

    from ntk.repositories.progress_note_repo import ProgressNoteRepo


@pytest.mark.parametrize(
    "note_type",
    [
        "MD Progress Note",
        "Nurse Practitioner Progress Note",
        "Nurse Practioner Progress Note",
        "NP/PA Progress Note",
    ],
)
def test_progress_note_types_are_always_sent_to_ai(note_type: str) -> None:
    note = ParsedProgressNote(
        note_type=note_type,
        note_text="No nutrition terminology is required.",
        raw_text="",
        source_filename="notes.pdf",
    )

    assert (
        PccProgressNotesExtractor._decide_note_action(note)  # noqa: SLF001
        is ProgressNoteAction.SEND_TO_AI
    )


@pytest.mark.parametrize(
    ("note_type", "note_text", "expected"),
    [
        ("Order Note", "Continue weekly weights.", ProgressNoteAction.SEND_TO_AI),
        (
            "Orders - Administration Note",
            "Resident refused Ensure.",
            ProgressNoteAction.SEND_TO_AI,
        ),
        (
            "Nursing Note",
            "PO intake was poor at lunch.",
            ProgressNoteAction.SEND_TO_AI,
        ),
        ("Nursing Notes", "Routine rounds completed.", ProgressNoteAction.FILTER),
        ("Order Note", "Medication administered.", ProgressNoteAction.FILTER),
        (
            "Social Work Note",
            "Resident discussed appetite.",
            ProgressNoteAction.SEND_TO_AI,
        ),
        (
            "Admission Note",
            "Resident was hospitalized before admission.",
            ProgressNoteAction.SEND_TO_AI,
        ),
    ],
)
def test_progress_note_action_filters_by_type_and_nutrition_terms(
    note_type: str,
    note_text: str,
    expected: ProgressNoteAction,
) -> None:
    note = ParsedProgressNote(
        note_type=note_type,
        note_text=note_text,
        raw_text="",
        source_filename="notes.pdf",
    )

    assert PccProgressNotesExtractor._decide_note_action(note) is expected  # noqa: SLF001


def test_extract_notes_removes_filtered_notes_before_ai_or_persistence(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    extractor = PccProgressNotesExtractor(tmp_path / "notes.pdf")
    split_notes = [
        ExtractedNote(
            raw_text=(
                "Effective Date: 08/20/2026\n"
                "Type: MD Progress Note\n"
                "Note Text: Routine follow-up."
            ),
            page_start=1,
            page_end=1,
            facility_resident_identifier="RES1",
        ),
        ExtractedNote(
            raw_text=(
                "Effective Date: 08/21/2026\n"
                "Type: Nursing Note\n"
                "Note Text: Routine rounds completed."
            ),
            page_start=1,
            page_end=1,
            facility_resident_identifier="RES1",
        ),
    ]
    monkeypatch.setattr(extractor, "_extract_document", list)
    monkeypatch.setattr(extractor, "_split_progress_notes", lambda _pages: split_notes)

    notes = extractor.extract_notes()

    assert len(notes) == 1
    assert notes[0].note_type == "MD Progress Note"


def test_extract_nutrition_notes_filters_by_note_type(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    extractor = PccProgressNotesExtractor(tmp_path / "notes.pdf")
    notes = [
        ParsedProgressNote(
            note_type=note_type,
            note_text="Assessment",
            raw_text="",
            source_filename="notes.pdf",
        )
        for note_type in (
            "Nutrition/Dietary Note",
            "Dietitian Progress Note",
            "MD Progress Note",
        )
    ]
    monkeypatch.setattr(extractor, "_parse_report_notes", lambda: notes)

    result = extractor.extract_nutrition_notes()

    assert [note.note_type for note in result] == [
        "Nutrition/Dietary Note",
        "Dietitian Progress Note",
    ]


def test_existing_progress_note_is_not_sent_to_ai(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    note = ParsedProgressNote(
        facility_resident_identifier="RES1",
        note_date=datetime(2026, 8, 20, tzinfo=UTC),
        note_type="MD Progress Note",
        author="Jane Doe, MD",
        note_text="Resident's appetite remains stable.",
        raw_text="",
        source_filename="notes.pdf",
    )
    expected_key = PccProgressNotesExtractor.get_note_key(
        facility_resident_identifier=note.facility_resident_identifier,
        effective_at=note.note_date,
        note_type=note.note_type,
        author=note.author,
        note_text=note.note_text,
    )
    assert note.note_date is not None
    note_date = note.note_date

    class ExistingProgressNoteRepo:
        def __init__(self) -> None:
            self.requested_keys: list[str] = []

        def get_by_key(self, note_key: str) -> ResidentProgressNote | None:
            self.requested_keys.append(note_key)
            if note_key != expected_key:
                return None
            return ResidentProgressNote(
                resident_id=7,
                note_date=note_date,
                note_text=note.note_text,
                raw_text=note.raw_text,
                note_key=note_key,
                extraction_status=ExtractionStatus.EXTRACTED,
            )

    repository = ExistingProgressNoteRepo()
    extractor = PccProgressNotesExtractor(
        tmp_path / "notes.pdf",
        progress_note_repository=repository,  # ty: ignore[invalid-argument-type]
    )
    agent_called = False

    async def run_agent(
        _extraction_input: ExtractionInput,
    ) -> ExtractedClinicalFacts:
        nonlocal agent_called
        agent_called = True
        return ExtractedClinicalFacts()

    monkeypatch.setattr(extractor, "extract_notes", lambda: [note])
    monkeypatch.setattr(extractor, "_run_data_extraction_agent", run_agent)

    assert asyncio.run(extractor.extract()) == []
    assert repository.requested_keys == [expected_key]
    assert not agent_called


def test_progress_note_is_persisted_before_ai_extraction(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    note = ParsedProgressNote(
        facility_resident_identifier="RES1",
        resident_name="Resident",
        facility_name="Facility",
        source_page=2,
        note_date=datetime(2026, 8, 20, tzinfo=UTC),
        note_type="MD Progress Note",
        author="Jane Doe, MD",
        note_text="Resident's appetite remains stable.",
        raw_text="Raw progress note",
        source_filename="notes.pdf",
    )
    events: list[str] = []

    class PersistingProgressNoteRepo:
        def __init__(self) -> None:
            self.note: ResidentProgressNote | None = None

        def get_by_key(self, _note_key: str) -> None:
            return None

        def create(self, progress_note: ResidentProgressNote) -> ResidentProgressNote:
            events.append("persisted")
            self.note = progress_note
            return progress_note

        def set_extraction_status(
            self,
            progress_note: ResidentProgressNote,
            status: ExtractionStatus,
        ) -> ResidentProgressNote:
            events.append(status.value)
            progress_note.extraction_status = status
            return progress_note

    repository = PersistingProgressNoteRepo()
    extractor = PccProgressNotesExtractor(
        tmp_path / "notes.pdf",
        progress_note_repository=repository,  # ty: ignore[invalid-argument-type]
        resident_resolver=lambda _note: ResidentResolution(resident_id=7),
    )

    async def run_agent(
        _extraction_input: ExtractionInput,
    ) -> ExtractedClinicalFacts:
        assert repository.note is not None
        assert repository.note.resident_id == 7  # noqa: PLR2004
        assert repository.note.extraction_status is ExtractionStatus.PENDING
        events.append("agent")
        return ExtractedClinicalFacts()

    monkeypatch.setattr(extractor, "extract_notes", lambda: [note])
    monkeypatch.setattr(extractor, "_run_data_extraction_agent", run_agent)

    assert asyncio.run(extractor.extract()) == []
    assert events == ["persisted", "agent"]
    assert repository.note is not None
    assert repository.note.extraction_status is ExtractionStatus.PENDING
    assert extractor.processed_progress_notes == [repository.note]
    assert repository.note.note_text == note.note_text
    assert repository.note.raw_text == note.raw_text


def test_progress_note_date_is_sent_to_ai_with_note_text(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    note_date = datetime(2026, 8, 20, tzinfo=UTC)
    note = ParsedProgressNote(
        facility_resident_identifier="RES1",
        note_date=note_date,
        note_type="MD Progress Note",
        author="Jane Doe, MD",
        note_text="Resident's appetite remains stable.",
        raw_text="",
        source_filename="notes.pdf",
    )

    class ProgressNoteRepo:
        def get_by_key(self, _note_key: str) -> None:
            return None

        @staticmethod
        def create(progress_note: ResidentProgressNote) -> ResidentProgressNote:
            return progress_note

        @staticmethod
        def set_extraction_status(
            progress_note: ResidentProgressNote,
            status: ExtractionStatus,
        ) -> ResidentProgressNote:
            progress_note.extraction_status = status
            return progress_note

    extractor = PccProgressNotesExtractor(
        tmp_path / "notes.pdf",
        progress_note_repository=ProgressNoteRepo(),  # ty: ignore[invalid-argument-type]
        resident_resolver=lambda _note: ResidentResolution(resident_id=7),
    )
    agent_inputs: list[ExtractionInput] = []

    async def run_agent(
        extraction_input: ExtractionInput,
    ) -> ExtractedClinicalFacts:
        agent_inputs.append(extraction_input)
        return ExtractedClinicalFacts()

    monkeypatch.setattr(extractor, "extract_notes", lambda: [note])
    monkeypatch.setattr(extractor, "_run_data_extraction_agent", run_agent)

    assert asyncio.run(extractor.extract()) == []
    assert agent_inputs == [
        ExtractionInput(
            text="Resident's appetite remains stable.",
            document_filename="notes.pdf",
            note_date=note_date,
        ),
    ]


def test_progress_notes_extract_concurrently_with_deduplication_and_isolated_failures(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    note_date = datetime(2026, 8, 20, tzinfo=UTC)

    def note(text: str, source_page: int) -> ParsedProgressNote:
        return ParsedProgressNote(
            facility_resident_identifier="RES1",
            resident_name="Resident One",
            facility_name="Facility One",
            source_page=source_page,
            note_date=note_date,
            note_type="MD Progress Note",
            author="Jane Doe, MD",
            note_text=text,
            raw_text=text,
            source_filename="notes.pdf",
        )

    notes = [
        note("Successful note A", 1),
        note("Successful note A", 9),
        note("Successful note B", 2),
        note("Fail this note", 3),
        note("Successful note C", 4),
    ]

    class ProgressNoteRepo:
        def __init__(self) -> None:
            self.next_id = 1
            self.statuses: list[tuple[str, ExtractionStatus]] = []

        @staticmethod
        def get_by_key(_note_key: str) -> None:
            return None

        def create(self, progress_note: ResidentProgressNote) -> ResidentProgressNote:
            progress_note.id = self.next_id
            self.next_id += 1
            return progress_note

        def set_extraction_status(
            self,
            progress_note: ResidentProgressNote,
            status: ExtractionStatus,
        ) -> ResidentProgressNote:
            self.statuses.append((progress_note.note_key, status))
            progress_note.extraction_status = status
            return progress_note

    repository = ProgressNoteRepo()
    extractor = PccProgressNotesExtractor(
        tmp_path / "notes.pdf",
        progress_note_repository=repository,  # ty: ignore[invalid-argument-type]
        resident_resolver=lambda _note: ResidentResolution(resident_id=7),
        concurrency=2,
    )
    active_calls = 0
    maximum_active_calls = 0
    agent_texts: list[str] = []

    class AgentUnavailableError(RuntimeError):
        pass

    async def run_agent(
        extraction_input: ExtractionInput,
    ) -> ExtractedClinicalFacts:
        nonlocal active_calls, maximum_active_calls
        active_calls += 1
        maximum_active_calls = max(maximum_active_calls, active_calls)
        agent_texts.append(extraction_input.text)
        try:
            await asyncio.sleep(0.01)
            if extraction_input.text == "Fail this note":
                raise AgentUnavailableError
            return ExtractedClinicalFacts(
                facts=[
                    AIExtractedClinicalFact(
                        payload=ClinicalFactPayload(
                            clinical_fact_type="observation",
                            observation_type="appetite",
                            description=extraction_input.text,
                            observed_at=note_date,
                        ),
                        confidence=1,
                    ),
                ],
            )
        finally:
            active_calls -= 1

    monkeypatch.setattr(extractor, "extract_notes", lambda: notes)
    monkeypatch.setattr(extractor, "_run_data_extraction_agent", run_agent)

    with caplog.at_level(logging.INFO):
        facts = asyncio.run(extractor.extract())

    assert maximum_active_calls == 2  # noqa: PLR2004
    assert agent_texts == [
        "Successful note A",
        "Successful note B",
        "Fail this note",
        "Successful note C",
    ]
    clinical_payloads = [
        fact.payload for fact in facts if isinstance(fact.payload, ClinicalFactPayload)
    ]
    assert [payload.description for payload in clinical_payloads] == [
        "Successful note A",
        "Successful note B",
        "Successful note C",
    ]
    assert [fact.source_page for fact in facts] == [1, 2, 4]
    assert [fact.progress_note_id for fact in facts] == [1, 2, 4]
    assert all(fact.resident_id == 7 for fact in facts)  # noqa: PLR2004
    assert len(extractor.processed_progress_notes) == 3  # noqa: PLR2004
    assert len(extractor.failed_progress_notes) == 1
    assert extractor.failed_progress_notes[0].note_text == "Fail this note"
    assert repository.statuses == [
        (extractor.failed_progress_notes[0].note_key, ExtractionStatus.FAILED),
    ]
    assert "notes=4 concurrency=2" in caplog.text
    assert "successes=3 failures=1" in caplog.text


def test_ai_clinical_fact_does_not_carry_demographic_updates(
    tmp_path: pathlib.Path,
) -> None:
    extractor = PccProgressNotesExtractor(tmp_path / "notes.pdf")
    note = ParsedProgressNote(
        facility_resident_identifier="RES-7",
        resident_name="Resident Seven",
        facility_name="Facility Seven",
        date_of_birth=date(1946, 2, 1),
        sex="f",
        height_in=64.5,
        note_text="Resident has fair intake.",
        raw_text="Resident has fair intake.",
        source_filename="notes.pdf",
    )
    progress_note = ResidentProgressNote(
        id=1,
        resident_id=7,
        note_date=datetime(2026, 8, 20, tzinfo=UTC),
        note_text=note.note_text,
        raw_text=note.raw_text,
        note_key="note-key",
        extraction_status=ExtractionStatus.PENDING,
    )
    ai_fact = AIExtractedClinicalFact(
        payload=ClinicalFactPayload(
            clinical_fact_type="observation",
            observation_type="appetite",
            observed_at=datetime(2026, 8, 20, tzinfo=UTC),
        ),
        confidence=1,
    )

    extracted_fact = extractor._build_fact_from_ai_output(  # noqa: SLF001
        note,
        progress_note,
        ai_fact,
    )

    assert extracted_fact.date_of_birth is None
    assert extracted_fact.sex is None
    assert extracted_fact.height_in is None
    assert extracted_fact.facility_resident_identifier == "RES-7"
    assert extracted_fact.resident_name == "Resident Seven"
    assert extracted_fact.facility_name == "Facility Seven"


def test_ai_wound_uses_progress_note_date_when_observed_at_is_missing(
    tmp_path: pathlib.Path,
) -> None:
    note_date = datetime(2026, 8, 20, tzinfo=UTC)
    extractor = PccProgressNotesExtractor(tmp_path / "notes.pdf")
    note = ParsedProgressNote(
        facility_resident_identifier="RES-7",
        source_page=3,
        note_date=note_date,
        note_text="Pressure injury documented without a separate wound date.",
        raw_text="Pressure injury documented without a separate wound date.",
        source_filename="notes.pdf",
    )
    progress_note = ResidentProgressNote(
        id=1,
        resident_id=7,
        note_date=note_date,
        note_text=note.note_text,
        raw_text=note.raw_text,
        note_key="wound-note-key",
        extraction_status=ExtractionStatus.PENDING,
    )
    ai_fact = AIExtractedClinicalFact(
        payload=WoundPayload(
            wound_type="Pressure injury",
            location=None,
            observed_at=None,
        ),
        confidence=1,
    )

    extracted_fact = extractor._build_fact_from_ai_output(  # noqa: SLF001
        note,
        progress_note,
        ai_fact,
    )

    assert isinstance(extracted_fact.payload, WoundPayload)
    assert extracted_fact.payload.observed_at == note_date
    assert extracted_fact.source_page == 3  # noqa: PLR2004


def test_clean_note_text_removes_page_and_duplicate_author_signature() -> None:
    text = (
        "Resident consumed 75% of lunch.\n"
        "Author: Jane Doe, RN [Nurse]\n"
        "[e-SIGNED] Signature: *****\n"
        "Page 1 of 1"
    )

    assert clean_note_text(text) == "Resident consumed 75% of lunch."


def test_parse_note_uses_cleaned_note_text(tmp_path: pathlib.Path) -> None:
    extractor = PccProgressNotesExtractor(tmp_path / "notes.pdf")
    split_note = ExtractedNote(
        raw_text=(
            "Effective Date: 08/20/2026\n"
            "Type: Nursing Note\n"
            "Author: Jane Doe, RN [Nurse]\n"
            "Note Text: Resident consumed 75% of lunch.\n"
            "Author: Jane Doe, RN [Nurse]\n"
            "[e-SIGNED] Signature: *****\n"
            "Page 1 of 1"
        ),
        page_start=1,
        page_end=1,
        facility_resident_identifier="RES1",
    )

    parsed_note = extractor._parse_note(split_note)  # noqa: SLF001

    assert parsed_note.author == "Jane Doe, RN"
    assert parsed_note.note_text == "Resident consumed 75% of lunch."
    assert "Author: Jane Doe, RN" in parsed_note.raw_text


def test_split_progress_notes_preserves_continuations_and_resident_changes() -> None:
    pages = [
        ExtractedNote(
            raw_text=(
                "Effective Date: 08/01/2026\nNote Text: First\n"
                "Effective Date: 08/02/2026\nNote Text: Second"
            ),
            page_start=1,
            page_end=1,
            facility_resident_identifier="R-1",
            resident_name="Resident One",
            facility_name="Facility",
        ),
        ExtractedNote(
            raw_text="continued text",
            page_start=2,
            page_end=2,
            facility_resident_identifier="R-1",
            resident_name="Resident One",
            facility_name="Facility",
        ),
        ExtractedNote(
            raw_text="Effective Date: 08/03/2026\nNote Text: Third",
            page_start=3,
            page_end=3,
            facility_resident_identifier="R-2",
            resident_name="Resident Two",
            facility_name="Facility",
        ),
    ]

    notes = PccProgressNotesExtractor._split_progress_notes(pages)  # noqa: SLF001

    assert len(notes) == 3  # noqa: PLR2004
    assert notes[1].page_start == 1
    assert notes[1].page_end == 2  # noqa: PLR2004
    assert notes[1].facility_resident_identifier == "R-1"
    assert notes[1].raw_text.endswith("continued text")
    assert notes[2].facility_resident_identifier == "R-2"


def test_progress_note_header_helpers_cover_gap_and_fallback_parsing() -> None:
    lines = [
        {"top": 0.0, "bottom": 10.0, "text": "Diagnoses"},
        {"top": 11.0, "bottom": 20.0, "text": "Malnutrition"},
        {"top": 80.0, "bottom": 90.0, "text": "Effective Date: 08/20/2026"},
    ]
    fallback_lines = [
        {"top": 0.0, "bottom": 10.0, "text": "Header"},
        {"top": 11.0, "bottom": 20.0, "text": "Effective Date: 08/21/2026"},
    ]

    assert PccProgressNotesExtractor._body_start_index(lines) == 2  # noqa: SLF001, PLR2004
    assert PccProgressNotesExtractor._body_start_index(fallback_lines) == 1  # noqa: SLF001
    assert PccProgressNotesExtractor._body_start_index([]) == 0  # noqa: SLF001
    assert PccProgressNotesExtractor._parse_resident("No resident") is None  # noqa: SLF001
    assert PccProgressNotesExtractor._parse_date_of_birth("No DOB") is None  # noqa: SLF001
    assert PccProgressNotesExtractor._parse_sex("No sex") is None  # noqa: SLF001


def test_progress_note_persistence_guard_branches(tmp_path: pathlib.Path) -> None:
    note = ParsedProgressNote(
        facility_resident_identifier="R-1",
        resident_name="Resident One",
        facility_name="Facility",
        note_date=datetime(2026, 8, 20, tzinfo=UTC),
        note_text="Note",
        raw_text="Note",
        source_filename="notes.pdf",
    )
    extractor = PccProgressNotesExtractor(tmp_path / "notes.pdf")

    with pytest.raises(RuntimeError, match="progress note repo"):
        extractor._get_or_create_progress_note(note, "key")  # noqa: SLF001

    class Repository:
        def __init__(self, existing: ResidentProgressNote | None = None) -> None:
            self.existing = existing
            self.statuses: list[ExtractionStatus] = []

        def get_by_key(self, _key: str) -> ResidentProgressNote | None:
            return self.existing

        def set_extraction_status(
            self,
            progress_note: ResidentProgressNote,
            status: ExtractionStatus,
        ) -> ResidentProgressNote:
            progress_note.extraction_status = status
            self.statuses.append(status)
            return progress_note

        @staticmethod
        def create(progress_note: ResidentProgressNote) -> ResidentProgressNote:
            return progress_note

    completed = ResidentProgressNote(
        id=1,
        resident_id=1,
        note_date=datetime(2026, 8, 20, tzinfo=UTC),
        note_text="Note",
        raw_text="Note",
        note_key="key",
        extraction_status=ExtractionStatus.EXTRACTED,
    )
    extractor.progress_note_repository = typing.cast(
        "ProgressNoteRepo",
        Repository(completed),
    )
    assert extractor._get_or_create_progress_note(note, "key") is None  # noqa: SLF001

    failed = completed.model_copy(update={"extraction_status": ExtractionStatus.FAILED})
    repository = Repository(failed)
    extractor.progress_note_repository = typing.cast("ProgressNoteRepo", repository)
    assert extractor._get_or_create_progress_note(note, "key") is failed  # noqa: SLF001
    assert repository.statuses == [ExtractionStatus.PENDING]

    extractor.progress_note_repository = typing.cast("ProgressNoteRepo", Repository())
    with pytest.raises(RuntimeError, match="resident ID resolver"):
        extractor._get_or_create_progress_note(note, "new-key")  # noqa: SLF001

    extractor.resident_resolver = lambda _note: None
    with pytest.raises(ValueError, match="Unable to resolve"):
        extractor._get_or_create_progress_note(note, "new-key")  # noqa: SLF001

    undated = note.model_copy(update={"note_date": None})
    with pytest.raises(ValueError, match="effective date"):
        extractor._get_or_create_progress_note(undated, "new-key")  # noqa: SLF001
