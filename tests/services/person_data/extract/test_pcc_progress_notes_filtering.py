from __future__ import annotations

import asyncio
import logging
import threading
import typing
from datetime import UTC, date, datetime

import pytest

from ntk.agents.data_extraction_agent import ExtractedClinicalFacts, ExtractionInput
from ntk.models.ai_extraction import AIExtractedClinicalFact
from ntk.models.extracted_fact_create import (
    AllergyPayload,
    ClinicalFactPayload,
    DiagnosisPayload,
    LabPayload,
    WoundPayload,
)
from ntk.models.sql.document import SourceAuthority
from ntk.models.sql.person import ExtractionStatus, PersonProgressNote
from ntk.pipelines.person.ingestion.extract.pcc_progress_notes import (
    ExtractedNote,
    ParsedHeaderDiagnosis,
    ParsedProgressNote,
    PccProgressNotesExtractor,
    PreparedProgressNoteExtraction,
    ProgressNoteAction,
    clean_note_text,
)

if typing.TYPE_CHECKING:
    import pathlib


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
            "Person refused Ensure.",
            ProgressNoteAction.SEND_TO_AI,
        ),
        (
            "Nursing Note",
            "PO intake was poor at lunch.",
            ProgressNoteAction.SEND_TO_AI,
        ),
        (
            "Nursing Note",
            "Resident was hospitalized for acute care.",
            ProgressNoteAction.SEND_TO_AI,
        ),
        ("Nursing Notes", "Routine rounds completed.", ProgressNoteAction.FILTER),
        ("Order Note", "Medication administered.", ProgressNoteAction.FILTER),
        (
            "Social Work Note",
            "Person discussed appetite.",
            ProgressNoteAction.SEND_TO_AI,
        ),
        (
            "Admission Note",
            "Person was hospitalized before admission.",
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


def test_resident_death_nursing_note_is_not_filtered() -> None:
    note_text = (
        "12am received patient in bed awake on the phone, pt denied any pain, "
        "distress or discomfort. At 4:30am patient complained of shortness of "
        "breath, oxygen 2L was given, head was elevated. At 4:40am writer went "
        "to check on patient, he was not responding to any physical touch or "
        "stimuli, vital signs was appreciated and supervisor was notified "
        "immediately, and patient was pronounced by RN. Dr was notified at "
        "4:45am and family notified at 4:48am. Postmortal care given. Sister "
        "called back at 5:30am, stating family will be here after 6am. Family "
        "came in and informed staff that funeral home will be coming by soon."
    )
    note = ParsedProgressNote(
        note_type="Nursing Note",
        note_text=note_text,
        raw_text=note_text,
        source_filename="notes.pdf",
    )

    assert (
        PccProgressNotesExtractor._decide_note_action(note)  # noqa: SLF001
        is ProgressNoteAction.SEND_TO_AI
    )
    assert PccProgressNotesExtractor.select_assessment_notes([note]) == [note]


def test_hospitalized_nursing_note_is_selected_for_assessment() -> None:
    note = ParsedProgressNote(
        note_type="Nursing Note",
        note_text="Resident was hospitalized for acute care.",
        raw_text="Resident was hospitalized for acute care.",
        source_filename="notes.pdf",
    )

    assert PccProgressNotesExtractor.select_assessment_notes([note]) == [note]


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
            source_person_identifier="RES1",
        ),
        ExtractedNote(
            raw_text=(
                "Effective Date: 08/21/2026\n"
                "Type: Nursing Note\n"
                "Note Text: Routine rounds completed."
            ),
            page_start=1,
            page_end=1,
            source_person_identifier="RES1",
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


def test_assessment_note_selection_keeps_clinical_notes_and_rejects_conflicts() -> None:
    def note(note_type: str, note_text: str, page: int) -> ParsedProgressNote:
        return ParsedProgressNote(
            source_person_identifier="210407",
            source_person_name="Dickow, Denise",
            source_page=page,
            note_type=note_type,
            note_text=note_text,
            raw_text=note_text,
            source_filename="notes.pdf",
        )

    notes = [
        note("Nutrition/Dietary Note", "Comprehensive nutrition assessment.", 1),
        note("Skilled Documentation", "GI and eating assistance reviewed.", 2),
        note("Nursing Note", "Unable to learn how to check blood sugar.", 3),
        note("Social Services", "SW will help reinstate SNAP benefits.", 4),
        note("Nursing Note", "Resident refused a scheduled medication.", 5),
        note("Social Services", "Housing application remains pending.", 6),
        note(
            "NP/PA Progress Note",
            "Yong Hua Fu is a n 80-year-old male seen for follow-up.",
            7,
        ),
    ]

    selected = PccProgressNotesExtractor.select_assessment_notes(notes)

    assert [(item.note_type, item.source_page) for item in selected] == [
        ("Nutrition/Dietary Note", 1),
        ("Skilled Documentation", 2),
        ("Nursing Note", 3),
        ("Social Services", 4),
    ]


def test_assessment_extraction_handles_administration_notes_deterministically(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def note(note_date: datetime, note_text: str, page: int) -> ParsedProgressNote:
        return ParsedProgressNote(
            source_person_identifier="210709",
            source_person_name="Davis, Fitzroy",
            source_page=page,
            note_date=note_date,
            note_type="Orders - Administration Note",
            note_text=note_text,
            raw_text=note_text,
            source_filename="notes.pdf",
        )

    first_date = datetime(2026, 8, 20, tzinfo=UTC)
    second_date = datetime(2026, 8, 21, tzinfo=UTC)
    notes = [
        note(first_date, "Humalog administered for bs 98.", 1),
        note(first_date, "Duplicate entry for BS: 98.", 2),
        note(second_date, "Resident refused treatment; BS 134.", 3),
        note(second_date, "Resident declined scheduled monitoring.", 4),
    ]
    extractor = PccProgressNotesExtractor(tmp_path / "notes.pdf")
    monkeypatch.setattr(extractor, "_parse_report_notes", lambda: notes)

    facts = asyncio.run(extractor.extract_for_assessment())

    lab_payloads = [
        fact.payload for fact in facts if isinstance(fact.payload, LabPayload)
    ]
    clinical_payloads = [
        fact.payload for fact in facts if isinstance(fact.payload, ClinicalFactPayload)
    ]
    assert [(payload.result, payload.observed_at) for payload in lab_payloads] == [
        ("98", first_date),
        ("134", second_date),
    ]
    assert len(clinical_payloads) == 1
    assert clinical_payloads[0].observation_type == "treatment_adherence"
    assert "2 administration notes" in (clinical_payloads[0].description or "")
    assert all(fact.extraction_method.value == "deterministic" for fact in facts)


def test_demo_progress_note_parsing_does_not_require_identity(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    extractor = PccProgressNotesExtractor(tmp_path / "notes.pdf")
    page = ExtractedNote(
        raw_text=(
            "Effective Date: 08/26/2026 15:11\n"
            "Type: Nursing\n"
            "Note Text: Resident consumed 75% of lunch."
        ),
        page_start=1,
        page_end=1,
    )
    monkeypatch.setattr(extractor, "_extract_document", lambda: [page])

    with pytest.raises(ValueError, match="Unable to determine the person"):
        extractor._parse_report_notes()  # noqa: SLF001

    notes = extractor._parse_report_notes(require_identity=False)  # noqa: SLF001

    assert len(notes) == 1
    assert notes[0].source_person_identifier is None
    assert notes[0].note_text == "Resident consumed 75% of lunch."


def test_progress_note_extractor_has_no_persistence_dependencies(
    tmp_path: pathlib.Path,
) -> None:
    extractor = PccProgressNotesExtractor(tmp_path / "notes.pdf")

    assert not hasattr(extractor, "progress_note_repository")
    assert not hasattr(extractor, "person_resolver")


def test_progress_note_is_persisted_before_ai_extraction(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    note = ParsedProgressNote(
        source_person_identifier="RES1",
        source_person_name="Person",
        facility_name="Facility",
        source_page=2,
        note_date=datetime(2026, 8, 20, tzinfo=UTC),
        note_type="MD Progress Note",
        author="Jane Doe, MD",
        note_text="Person's appetite remains stable.",
        raw_text="Raw progress note",
        source_filename="notes.pdf",
    )
    events: list[str] = []

    class PersistingProgressNoteRepo:
        def __init__(self) -> None:
            self.note: PersonProgressNote | None = None

        def get_by_key(self, _note_key: str) -> None:
            return None

        def create(self, progress_note: PersonProgressNote) -> PersonProgressNote:
            events.append("persisted")
            self.note = progress_note
            return progress_note

        def set_extraction_status(
            self,
            progress_note: PersonProgressNote,
            status: ExtractionStatus,
        ) -> PersonProgressNote:
            events.append(status.value)
            progress_note.extraction_status = status
            return progress_note

    repository = PersistingProgressNoteRepo()
    extractor = PccProgressNotesExtractor(tmp_path / "notes.pdf")

    async def run_agent(
        _extraction_input: ExtractionInput,
    ) -> ExtractedClinicalFacts:
        assert repository.note is not None
        assert repository.note.person_id == 7  # noqa: PLR2004
        assert repository.note.extraction_status is ExtractionStatus.PENDING
        events.append("agent")
        return ExtractedClinicalFacts()

    progress_note = PersonProgressNote(
        id=1,
        person_id=7,
        note_date=note.note_date,  # ty: ignore[invalid-argument-type]
        note_text=note.note_text,
        raw_text=note.raw_text,
        note_key="key",
        extraction_status=ExtractionStatus.PENDING,
    )
    repository.create(progress_note)
    monkeypatch.setattr(extractor, "_run_data_extraction_agent", run_agent)

    outcomes = asyncio.run(
        extractor.extract_prepared(
            [PreparedProgressNoteExtraction(note, 7, progress_note.id)],
        ),
    )
    assert outcomes[0].error is None
    assert events == ["persisted", "agent"]
    assert repository.note is not None
    assert repository.note.extraction_status is ExtractionStatus.PENDING
    assert repository.note.note_text == note.note_text
    assert repository.note.raw_text == note.raw_text


def test_progress_note_date_is_sent_to_ai_with_note_text(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    note_date = datetime(2026, 8, 20, tzinfo=UTC)
    note = ParsedProgressNote(
        source_person_identifier="RES1",
        note_date=note_date,
        note_type="MD Progress Note",
        author="Jane Doe, MD",
        note_text="Person's appetite remains stable.",
        raw_text="",
        source_filename="notes.pdf",
    )

    extractor = PccProgressNotesExtractor(tmp_path / "notes.pdf")
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
            text="Person's appetite remains stable.",
            document_filename="notes.pdf",
            note_date=note_date,
        ),
    ]


def test_progress_notes_use_bounded_async_concurrency_with_isolated_failures(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    note_date = datetime(2026, 8, 20, tzinfo=UTC)

    def note(text: str, source_page: int) -> ParsedProgressNote:
        return ParsedProgressNote(
            source_person_identifier="RES1",
            source_person_name="Person One",
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

    extractor = PccProgressNotesExtractor(tmp_path / "notes.pdf", concurrency=2)
    active_calls = 0
    maximum_active_calls = 0
    agent_texts: list[str] = []
    worker_threads: set[int] = set()

    class AgentUnavailableError(RuntimeError):
        pass

    async def run_agent(
        extraction_input: ExtractionInput,
    ) -> ExtractedClinicalFacts:
        nonlocal active_calls, maximum_active_calls
        worker_threads.add(threading.get_ident())
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

    monkeypatch.setattr(extractor, "_run_data_extraction_agent", run_agent)
    prepared = [
        PreparedProgressNoteExtraction(note=item, person_id=7, progress_note_id=index)
        for index, (_key, item) in enumerate(
            extractor.deduplicate_notes(notes),
            start=1,
        )
    ]

    with caplog.at_level(logging.INFO):
        outcomes = asyncio.run(extractor.extract_prepared(prepared))
    facts = [fact for outcome in outcomes for fact in outcome.facts or ()]

    assert maximum_active_calls == 2  # noqa: PLR2004
    assert worker_threads == {threading.get_ident()}
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
    assert all(fact.person_id == 7 for fact in facts)  # noqa: PLR2004
    assert len([outcome for outcome in outcomes if outcome.error]) == 1
    assert "notes=4 concurrency=2" in caplog.text
    assert "failures=1" in caplog.text


def test_ai_clinical_fact_does_not_carry_demographic_updates(
    tmp_path: pathlib.Path,
) -> None:
    extractor = PccProgressNotesExtractor(tmp_path / "notes.pdf")
    note = ParsedProgressNote(
        source_person_identifier="RES-7",
        source_person_name="Person Seven",
        facility_name="Facility Seven",
        date_of_birth=date(1946, 2, 1),
        sex="f",
        height_in=64.5,
        note_text="Person has fair intake.",
        raw_text="Person has fair intake.",
        source_filename="notes.pdf",
    )
    progress_note = PersonProgressNote(
        id=1,
        person_id=7,
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
    assert extracted_fact.source_person_identifier == "RES-7"
    assert extracted_fact.source_person_name == "Person Seven"
    assert extracted_fact.facility_name == "Facility Seven"


def test_ai_wound_uses_progress_note_date_when_observed_at_is_missing(
    tmp_path: pathlib.Path,
) -> None:
    note_date = datetime(2026, 8, 20, tzinfo=UTC)
    extractor = PccProgressNotesExtractor(tmp_path / "notes.pdf")
    note = ParsedProgressNote(
        source_person_identifier="RES-7",
        source_page=3,
        note_date=note_date,
        note_text="Pressure injury documented without a separate wound date.",
        raw_text="Pressure injury documented without a separate wound date.",
        source_filename="notes.pdf",
    )
    progress_note = PersonProgressNote(
        id=1,
        person_id=7,
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
        "Person consumed 75% of lunch.\n"
        "Author: Jane Doe, RN [Nurse]\n"
        "[e-SIGNED] Signature: *****\n"
        "Page 1 of 1"
    )

    assert clean_note_text(text) == "Person consumed 75% of lunch."


def test_parse_note_uses_cleaned_note_text(tmp_path: pathlib.Path) -> None:
    extractor = PccProgressNotesExtractor(tmp_path / "notes.pdf")
    split_note = ExtractedNote(
        raw_text=(
            "Effective Date: 08/20/2026\n"
            "Type: Nursing Note\n"
            "Author: Jane Doe, RN [Nurse]\n"
            "Note Text: Person consumed 75% of lunch.\n"
            "Author: Jane Doe, RN [Nurse]\n"
            "[e-SIGNED] Signature: *****\n"
            "Page 1 of 1"
        ),
        page_start=1,
        page_end=1,
        source_person_identifier="RES1",
    )

    parsed_note = extractor._parse_note(split_note)  # noqa: SLF001

    assert parsed_note.author == "Jane Doe, RN"
    assert parsed_note.note_text == "Person consumed 75% of lunch."
    assert "Author: Jane Doe, RN" in parsed_note.raw_text


def test_split_progress_notes_preserves_continuations_and_person_changes() -> None:
    pages = [
        ExtractedNote(
            raw_text=(
                "Effective Date: 08/01/2026\nNote Text: First\n"
                "Effective Date: 08/02/2026\nNote Text: Second"
            ),
            page_start=1,
            page_end=1,
            source_person_identifier="R-1",
            source_person_name="Person One",
            facility_name="Facility",
        ),
        ExtractedNote(
            raw_text="continued text",
            page_start=2,
            page_end=2,
            source_person_identifier="R-1",
            source_person_name="Person One",
            facility_name="Facility",
        ),
        ExtractedNote(
            raw_text="Effective Date: 08/03/2026\nNote Text: Third",
            page_start=3,
            page_end=3,
            source_person_identifier="R-2",
            source_person_name="Person Two",
            facility_name="Facility",
        ),
    ]

    notes = PccProgressNotesExtractor._split_progress_notes(pages)  # noqa: SLF001

    assert len(notes) == 3  # noqa: PLR2004
    assert notes[1].page_start == 1
    assert notes[1].page_end == 2  # noqa: PLR2004
    assert notes[1].source_person_identifier == "R-1"
    assert notes[1].raw_text.endswith("continued text")
    assert notes[2].source_person_identifier == "R-2"


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
    assert PccProgressNotesExtractor._parse_person("No person") is None  # noqa: SLF001
    assert PccProgressNotesExtractor._parse_date_of_birth("No DOB") is None  # noqa: SLF001
    assert PccProgressNotesExtractor._parse_sex("No sex") is None  # noqa: SLF001


def test_progress_note_header_fields_are_extracted_deterministically(
    tmp_path: pathlib.Path,
) -> None:
    header = (
        "Date: Sep 9, 2026\n"
        "Resident Name :\nKeitt-jones, Bertha (EN140516)\n"
        "Medical Record # : EN140516\n"
        "Gender :\nF\n"
        "Date of Birth : 08/07/1944\n"
        "Allergies :\nAMOXICILLIN/CLAVULANIC ACID, Lactose, Sulfur\n"
        "Diagnoses :\n"
        "TRANSIENT CEREBRAL ISCHEMIC ATTACK, UNSPECIFIED(G45.9), "
        "SICKLE-CELL TRAIT\n(D57.3)\n"
        "Effective Date: 09/09/2026 08:27\n"
    )
    extractor = PccProgressNotesExtractor(tmp_path / "notes.pdf")

    identifier = extractor._parse_medical_record_identifier(header)  # noqa: SLF001
    assert identifier == "EN140516"
    assert extractor._parse_date_of_birth(header) == date(1944, 8, 7)  # noqa: SLF001
    assert extractor._parse_sex(header) == "f"  # noqa: SLF001
    assert extractor._parse_allergies(header) == (  # noqa: SLF001
        ("AMOXICILLIN/CLAVULANIC ACID", "Lactose", "Sulfur"),
        False,
    )
    diagnoses = extractor._parse_diagnoses(header)  # noqa: SLF001
    assert [(item.diagnosis, item.code) for item in diagnoses] == [
        ("TRANSIENT CEREBRAL ISCHEMIC ATTACK, UNSPECIFIED", "G45.9"),
        ("SICKLE-CELL TRAIT", "D57.3"),
    ]


def test_progress_note_header_facts_are_unique_and_keep_demographics(
    tmp_path: pathlib.Path,
) -> None:
    observed_at = datetime(2026, 9, 9, tzinfo=UTC)
    extractor = PccProgressNotesExtractor(tmp_path / "notes.pdf")
    note = ParsedProgressNote(
        source_person_identifier="EN140516",
        source_person_name="Keitt-jones, Bertha",
        date_of_birth=date(1944, 8, 7),
        sex="f",
        source_page=1,
        report_observed_at=observed_at,
        allergies=("Lactose",),
        diagnoses=(
            ParsedHeaderDiagnosis(
                diagnosis="END STAGE RENAL DISEASE",
                code="N18.6",
            ),
        ),
        note_text="Routine note.",
        raw_text="Routine note.",
        source_filename="notes.pdf",
    )

    facts = extractor.extract_header_facts([note, note.model_copy()])

    assert len(facts) == 2  # noqa: PLR2004
    allergy = next(fact for fact in facts if isinstance(fact.payload, AllergyPayload))
    diagnosis = next(
        fact for fact in facts if isinstance(fact.payload, DiagnosisPayload)
    )
    allergy_payload = typing.cast("AllergyPayload", allergy.payload)
    diagnosis_payload = typing.cast("DiagnosisPayload", diagnosis.payload)
    assert allergy_payload.allergen == "Lactose"
    assert diagnosis_payload.code == "N18.6"
    assert diagnosis_payload.code_system == "ICD-10-CM"
    assert all(fact.date_of_birth == date(1944, 8, 7) for fact in facts)
    assert all(fact.sex == "f" for fact in facts)
    assert all(fact.source_person_identifier == "EN140516" for fact in facts)
    assert all(
        fact.source_authority is SourceAuthority.STRUCTURED_RECORD for fact in facts
    )
