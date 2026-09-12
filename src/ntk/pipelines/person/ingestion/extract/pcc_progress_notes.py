from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import time
import typing
import unicodedata
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum

import pymupdf
from pydantic import BaseModel

from ntk.agents.data_extraction_agent import (
    DATA_EXTRACTION_MODEL,
    DataExtractionAgent,
    ExtractedClinicalFacts,
    ExtractionInput,
)
from ntk.models.extracted_fact_create import (
    AllergyPayload,
    ClinicalFactPayload,
    DiagnosisPayload,
    ExtractedFactCreate,
    LabPayload,
)
from ntk.models.settings import SETTINGS
from ntk.models.sql.clinical.common import ClinicalStatus
from ntk.models.sql.document import SourceAuthority
from ntk.models.sql.extracted_fact import ExtractionMethod

from .base import PersonExtractor
from .registry import register_extractor

if typing.TYPE_CHECKING:
    import pathlib

    from ntk.models.ai_extraction import AIExtractedClinicalFact
    from ntk.models.extracted_fact_create import FactPayload
    from ntk.models.sql.person import PersonProgressNote


logger = logging.getLogger(__name__)


_PERSON_ID_RE = re.compile(
    r"\bResident(?:\s+Name)?\s*:\s*(?P<name>[^(]+?)\s*"
    r"\((?P<id>[A-Z]{0,4}\d+)\)",
)
_MEDICAL_RECORD_RE = re.compile(
    r"\bMedical\s+Record\s*#\s*:\s*(?P<id>[A-Z0-9-]+)\b",
    flags=re.IGNORECASE,
)
_DOB_RE = re.compile(
    r"\b(?:DOB|Date\s+of\s+Birth)\s*:?\s*"
    r"(?P<date>\d{1,2}/\d{1,2}/\d{4})\b",
    flags=re.IGNORECASE,
)
_SEX_RE = re.compile(
    r"\b(?:Sex|Gender)\s*:\s*(?P<sex>Female|Male|F|M)\b",
    flags=re.IGNORECASE,
)
_EFFECTIVE_DATE_RE = re.compile(
    r"^Effective Date\s*:\s*(?P<date>\d{1,2}/\d{1,2}/\d{4})",
    flags=re.IGNORECASE,
)
_REPORT_DATE_RE = re.compile(
    r"(?m)^Date\s*:\s*(?P<date>"
    r"(?:[A-Za-z]{3,9}\s+\d{1,2},\s+\d{4})|"
    r"(?:\d{1,2}/\d{1,2}/\d{4})"
    r")\s*$",
    flags=re.IGNORECASE,
)
_ALLERGIES_BLOCK_RE = re.compile(
    r"\bAllergies\s*:\s*(?P<value>.*?)\s*\bDiagnoses\s*:",
    flags=re.IGNORECASE | re.DOTALL,
)
_DIAGNOSES_BLOCK_RE = re.compile(
    r"\bDiagnoses\s*:\s*(?P<value>.*?)\s*\bEffective\s+Date\s*:",
    flags=re.IGNORECASE | re.DOTALL,
)
_DIAGNOSIS_RE = re.compile(
    r"(?P<diagnosis>.*?)\s*\((?P<code>[A-Z][A-Z0-9.]*)\)\s*(?:,|$)",
)
_NO_KNOWN_ALLERGIES = {
    "nka",
    "nkda",
    "no known allergies",
    "no known drug allergies",
}
_PAGE_RE = re.compile(r"(?m)^Page \d+ of \d+\s*$")
_TRAILING_SIGNATURE_RE = re.compile(
    r"(?ms)\n?Author:.*?\[e-SIGNED\]\s*Signature:\s*(?:\*+|_+)\s*$",
)
_AUTHOR_LINE_RE = re.compile(
    r"^Author\s*:\s*(?P<author>.*?)(?:\s*\[.*)?$",
    flags=re.IGNORECASE | re.MULTILINE,
)
_NOTE_TYPE_RE = re.compile(
    r"Type:\s*(?P<type>.+)$",
    flags=re.IGNORECASE | re.MULTILINE,
)
_NOTE_TEXT_RE = re.compile(
    r"^Note Text\s*:\s*(?P<text>.*)",
    flags=re.IGNORECASE | re.MULTILINE | re.DOTALL,
)
_LINE_Y_TOLERANCE = 2.0
_HEADER_GAP_THRESHOLD = 10.0

NUTRITION_TERMS = {
    "weight",
    "appetite",
    "intake",
    "po intake",
    "diet",
    "supplement",
    "ensure",
    "glucerna",
    "prostat",
    "tube feed",
    "feeding",
    "peg",
    "npo",
    "refused",
    "declined",
    "nausea",
    "vomiting",
    "diarrhea",
    "constipation",
    "edema",
    "dehydration",
    "fluid",
    "sodium",
    "potassium",
    "bun",
    "creatinine",
    "gfr",
    "albumin",
    "a1c",
    "glucose",
    "wound",
    "pressure ulcer",
    "dialysis",
    "hospitalized",
}
_ALWAYS_EXTRACT_NOTE_TYPES = {
    "md progress note",
    "nurse practitioner progress note",
    # Retain compatibility with the spelling used by some PCC facilities.
    "nurse practioner progress note",
    "np/pa progress note",
}
_NUTRITION_FILTERED_NOTE_TYPES = {
    "order note",
    "orders - administration note",
}
_NUTRITION_ASSESSMENT_TYPE_TERMS = (
    "dietary",
    "dietitian",
    "dietician",
    "nutrition",
)
_NUTRITION_TERM_RE = re.compile(
    r"(?<!\w)(?:"
    + "|".join(
        re.escape(term).replace(r"\ ", r"\s+")
        for term in sorted(NUTRITION_TERMS, key=len, reverse=True)
    )
    + r")(?:s|es)?(?!\w)",
    flags=re.IGNORECASE,
)
_ASSESSMENT_NOTE_TYPE_TERMS = (
    "dietary",
    "dietitian",
    "dietician",
    "nutrition",
    "skilled documentation",
    "skin",
    "wound",
)
_ASSESSMENT_CLINICAL_TERM_RE = re.compile(
    r"(?<!\w)(?:"
    r"weight|appetite|meal|po\s+intake|intake|diet|supplement|ensure|glucerna|"
    r"prostat|tube\s+feed|feeding|peg|npo|chew(?:ing)?|swallow(?:ing)?|dysphagia|"
    r"nausea|vomiting|diarrhea|constipation|edema|dehydration|fluid\s+restriction|"
    r"blood\s+sugar|glucose|hypoglyc(?:emia|emic)|hyperglyc(?:emia|emic)|wound|"
    r"pressure\s+(?:ulcer|injury)|dialysis|hospitali[sz]ed"
    r")(?!\w)",
    flags=re.IGNORECASE,
)
_ASSESSMENT_SOCIAL_TERM_RE = re.compile(
    r"(?<!\w)(?:food\s+insecurity|food\s+access|meal\s+(?:access|delivery|support)|"
    r"grocer(?:y|ies)|snap|kitchen|home\s+delivered\s+meal)(?!\w)",
    flags=re.IGNORECASE,
)
_CRITICAL_CLINICAL_EVENT_RE = re.compile(
    r"(?<!\w)(?:"
    r"death|died|deceased|expired|passed\s+away|"
    r"pronounced\s+(?:dead|deceased)|"
    r"pronounced\s+by\s+(?:(?:an?|the)\s+)?(?:rn|nurse|physician|doctor|md)|"
    r"post\s*-?\s*mort(?:al|em)\s+care|funeral\s+home"
    r")(?!\w)",
    flags=re.IGNORECASE,
)
_EXPLICIT_PATIENT_NAME_RE = re.compile(
    r"\b(?P<name>[A-Z][A-Za-z'-]+(?:\s+[A-Z][A-Za-z'-]+){1,3})\s+is\s+"
    r"a(?:\s*n)?\s+\d{1,3}\s*-\s*year-old\b",
)
_REFUSAL_RE = re.compile(
    r"\b(?:refus(?:e|ed|ing)|declin(?:e|ed|ing))\b",
    re.IGNORECASE,
)
_POINT_OF_CARE_GLUCOSE_RE = re.compile(
    r"\bbs\s*:?\s*(?P<value>\d{2,3})\b",
    re.IGNORECASE,
)
_ADMINISTRATION_NOTE_TYPE = "orders - administration note"
_MIN_PERSON_NAME_TOKENS = 2

Word = tuple[float, float, float, float, str, int, int, int]


def clean_note_text(text: str) -> str:
    """Remove repeated author signatures and page markers from note text."""
    text = _PAGE_RE.sub("", text)
    text = _TRAILING_SIGNATURE_RE.sub("", text)
    return text.strip()


class ProgressNoteAction(StrEnum):
    """Action to take after parsing a progress note."""

    FILTER = "filter"
    SEND_TO_AI = "send_to_ai"


class ParsedHeaderDiagnosis(BaseModel):
    """One diagnosis and code read from a structured PCC report header."""

    diagnosis: str
    code: str | None = None


class ExtractedNote(BaseModel):
    """Text extracted from one page or one note with source identity."""

    raw_text: str
    page_start: int
    page_end: int
    source_person_identifier: str | None = None
    source_person_name: str | None = None
    facility_name: str | None = None
    date_of_birth: date | None = None
    sex: str | None = None
    height_in: float | None = None
    report_observed_at: datetime | None = None
    allergies: tuple[str, ...] = ()
    no_known_allergies: bool = False
    diagnoses: tuple[ParsedHeaderDiagnosis, ...] = ()


class ParsedProgressNote(BaseModel):
    source_person_identifier: str | None = None
    source_person_name: str | None = None
    facility_name: str | None = None
    date_of_birth: date | None = None
    sex: str | None = None
    height_in: float | None = None
    report_observed_at: datetime | None = None
    allergies: tuple[str, ...] = ()
    no_known_allergies: bool = False
    diagnoses: tuple[ParsedHeaderDiagnosis, ...] = ()
    source_page: int | None = None
    note_date: datetime | None = None
    note_type: str | None = None
    author: str | None = None
    note_text: str
    raw_text: str
    source_filename: str


@dataclass(frozen=True, slots=True)
class PreparedProgressNoteExtraction:
    """Session-free values needed by one concurrent AI extraction task."""

    note: ParsedProgressNote
    person_id: int | None
    progress_note_id: int | None


@dataclass(frozen=True, slots=True)
class ProgressNoteExtractionOutcome:
    """Facts or an error produced for one prepared progress note."""

    prepared: PreparedProgressNoteExtraction
    facts: list[ExtractedFactCreate] | None = None
    error: BaseException | None = None


@register_extractor
class PccProgressNotesExtractor(PersonExtractor):
    """Recognize and extract a PCC progress-notes report."""

    def __init__(
        self,
        path: pathlib.Path,
        concurrency: int | None = None,
    ) -> None:
        """Initialize the persistence-free progress-note extractor."""
        super().__init__(path)
        resolved_concurrency = (
            SETTINGS.progress_note_extraction_concurrency
            if concurrency is None
            else concurrency
        )
        if resolved_concurrency < 1:
            msg = "Progress-note extraction concurrency must be at least 1"
            raise ValueError(msg)
        self.concurrency = resolved_concurrency
        self._last_parsed_notes: list[ParsedProgressNote] | None = None

    def is_expected_format(self) -> bool:
        """Return whether the document is a PCC progress-notes report."""
        return self._is_pdf(self.path) and self._first_page_contains(
            "Progress Notes *NEW*",
        )

    async def extract(self) -> list[ExtractedFactCreate]:
        """Extract facts without resolving or persisting person identity."""
        notes = self.extract_notes()
        facts = await self._extract_note_facts(notes)
        facts.extend(self.extract_header_facts())
        return facts

    async def extract_for_assessment(self) -> list[ExtractedFactCreate]:
        """Extract an assessment-focused, provenance-preserving fact set."""
        notes = self._parse_report_notes()
        selected_notes = self.select_assessment_notes(notes)
        facts = await self._extract_note_facts(selected_notes)
        facts.extend(self._extract_administration_facts(notes))
        facts.extend(self.extract_header_facts(notes))
        return facts

    async def extract_for_demo(self) -> list[ExtractedFactCreate]:
        """Extract assessment facts without requiring source identity fields."""
        notes = self._parse_report_notes(require_identity=False)
        selected_notes = self.select_assessment_notes(notes)
        facts = await self._extract_note_facts(selected_notes)
        facts.extend(self._extract_administration_facts(notes))
        facts.extend(self.extract_header_facts(notes))
        return facts

    def extract_header_facts(
        self,
        notes: list[ParsedProgressNote] | None = None,
    ) -> list[ExtractedFactCreate]:
        """Return unique allergies and diagnoses from structured report headers."""
        source_notes = notes if notes is not None else self._last_parsed_notes or []
        facts: list[ExtractedFactCreate] = []
        seen: set[tuple[str | None, str, str]] = set()
        for note in source_notes:
            for allergen in note.allergies:
                key = (
                    note.source_person_identifier,
                    "allergy",
                    self._normalize_text(allergen),
                )
                if key in seen:
                    continue
                seen.add(key)
                facts.append(
                    self._build_deterministic_fact(
                        note,
                        AllergyPayload(
                            allergen=allergen,
                            status=ClinicalStatus.ACTIVE,
                            observed_at=note.report_observed_at,
                        ),
                        source_record_type="progress_note_header",
                        source_authority=SourceAuthority.STRUCTURED_RECORD,
                    ),
                )
            if note.no_known_allergies:
                key = (note.source_person_identifier, "allergy", "no_known_allergies")
                if key not in seen:
                    seen.add(key)
                    facts.append(
                        self._build_deterministic_fact(
                            note,
                            AllergyPayload(
                                no_known_allergies=True,
                                status=ClinicalStatus.ACTIVE,
                                observed_at=note.report_observed_at,
                            ),
                            source_record_type="progress_note_header",
                            source_authority=SourceAuthority.STRUCTURED_RECORD,
                        ),
                    )
            for diagnosis in note.diagnoses:
                identity = diagnosis.code or self._normalize_text(diagnosis.diagnosis)
                key = (note.source_person_identifier, "diagnosis", identity)
                if key in seen:
                    continue
                seen.add(key)
                facts.append(
                    self._build_deterministic_fact(
                        note,
                        DiagnosisPayload(
                            diagnosis=diagnosis.diagnosis,
                            code=diagnosis.code,
                            code_system="ICD-10-CM" if diagnosis.code else None,
                            status=ClinicalStatus.ACTIVE,
                            observed_at=note.report_observed_at,
                        ),
                        source_record_type="progress_note_header",
                        source_authority=SourceAuthority.STRUCTURED_RECORD,
                    ),
                )
        return facts

    def report_identity_notes(self) -> list[ParsedProgressNote]:
        """Return one parsed header identity per resident represented in the report."""
        identities: dict[tuple[str | None, str | None], ParsedProgressNote] = {}
        for note in self._last_parsed_notes or ():
            key = (note.source_person_identifier, note.source_person_name)
            if any(key):
                identities.setdefault(key, note)
        return list(identities.values())

    async def _extract_note_facts(
        self,
        notes: list[ParsedProgressNote],
    ) -> list[ExtractedFactCreate]:
        """Extract facts from supplied notes while preserving note provenance."""
        prepared = [
            PreparedProgressNoteExtraction(
                note=note,
                person_id=None,
                progress_note_id=None,
            )
            for _note_key, note in self.deduplicate_notes(notes)
        ]
        outcomes = await self.extract_prepared(prepared)
        errors = [outcome.error for outcome in outcomes if outcome.error is not None]
        facts = [fact for outcome in outcomes for fact in outcome.facts or ()]
        if not facts and errors:
            raise errors[0]
        return facts

    @classmethod
    def select_assessment_notes(
        cls,
        notes: list[ParsedProgressNote],
    ) -> list[ParsedProgressNote]:
        """Keep clinically useful notes and reject explicit identity conflicts."""
        selected: list[ParsedProgressNote] = []
        for note in notes:
            note_type = cls._normalize_text(note.note_type or "")
            if note_type == _ADMINISTRATION_NOTE_TYPE:
                continue
            if cls._has_explicit_identity_conflict(note):
                logger.warning(
                    "Skipping progress note on page %s because its body names a "
                    "different person than the report header",
                    note.source_page,
                )
                continue
            if _CRITICAL_CLINICAL_EVENT_RE.search(note.note_text):
                selected.append(note)
                continue
            if note_type in _ALWAYS_EXTRACT_NOTE_TYPES or any(
                term in note_type for term in _ASSESSMENT_NOTE_TYPE_TERMS
            ):
                selected.append(note)
                continue
            if note_type.startswith("social"):
                if _ASSESSMENT_SOCIAL_TERM_RE.search(note.note_text):
                    selected.append(note)
                continue
            if _ASSESSMENT_CLINICAL_TERM_RE.search(note.note_text):
                selected.append(note)
        return selected

    @classmethod
    def _has_explicit_identity_conflict(cls, note: ParsedProgressNote) -> bool:
        source_tokens = cls._person_name_tokens(note.source_person_name)
        if len(source_tokens) < _MIN_PERSON_NAME_TOKENS:
            return False
        match = _EXPLICIT_PATIENT_NAME_RE.search(note.note_text)
        if match is None:
            return False
        named_tokens = cls._person_name_tokens(match.group("name"))
        return len(named_tokens) >= _MIN_PERSON_NAME_TOKENS and (
            named_tokens[0],
            named_tokens[-1],
        ) != (source_tokens[0], source_tokens[-1])

    @classmethod
    def _person_name_tokens(cls, name: str | None) -> list[str]:
        if not name:
            return []
        if "," in name:
            last_name, given_names = name.split(",", maxsplit=1)
            name = f"{given_names} {last_name}"
        return re.findall(r"[a-z]+", cls._normalize_text(name))

    @classmethod
    def _extract_administration_facts(
        cls,
        notes: list[ParsedProgressNote],
    ) -> list[ExtractedFactCreate]:
        """Summarize repetitive administration data without model requests."""
        administration_notes = [
            note
            for note in notes
            if cls._normalize_text(note.note_type or "") == _ADMINISTRATION_NOTE_TYPE
        ]
        facts: list[ExtractedFactCreate] = []
        seen_glucose: set[tuple[datetime, str]] = set()
        for note in administration_notes:
            if note.note_date is None:
                continue
            for match in _POINT_OF_CARE_GLUCOSE_RE.finditer(note.note_text):
                value = match.group("value")
                identity = (note.note_date, value)
                if identity in seen_glucose:
                    continue
                seen_glucose.add(identity)
                facts.append(
                    cls._build_deterministic_fact(
                        note,
                        LabPayload(
                            name="Point-of-care glucose",
                            result=value,
                            unit="mg/dL",
                            observed_at=note.note_date,
                        ),
                    ),
                )

        refusal_notes = [
            note for note in administration_notes if _REFUSAL_RE.search(note.note_text)
        ]
        dated_refusals = [note for note in refusal_notes if note.note_date is not None]
        if dated_refusals:
            latest = max(
                dated_refusals,
                key=lambda note: typing.cast("datetime", note.note_date),
            )
            facts.append(
                cls._build_deterministic_fact(
                    latest,
                    ClinicalFactPayload(
                        clinical_fact_type="observation",
                        observation_type="treatment_adherence",
                        status="recurrent refusal",
                        description=(
                            "Repeated medication, treatment, or monitoring refusals "
                            f"were documented in {len(refusal_notes)} administration "
                            "notes during the report period."
                        ),
                        observed_at=latest.note_date,
                    ),
                ),
            )
        return facts

    @staticmethod
    def _build_deterministic_fact(
        note: ParsedProgressNote,
        payload: FactPayload,
        *,
        source_record_type: str | None = None,
        source_authority: SourceAuthority = SourceAuthority.CLINICAL_DOCUMENT,
    ) -> ExtractedFactCreate:
        """Attach report identity and page provenance to a derived source fact."""
        return ExtractedFactCreate(
            payload=payload,
            confidence=1,
            extraction_method=ExtractionMethod.DETERMINISTIC,
            source_person_identifier=note.source_person_identifier,
            source_person_name=note.source_person_name,
            facility_name=note.facility_name,
            date_of_birth=note.date_of_birth,
            sex=note.sex,
            height_in=note.height_in,
            source_page=note.source_page,
            source_system="pointclickcare",
            source_record_type=source_record_type or note.note_type,
            source_authority=source_authority,
        )

    async def extract_prepared(
        self,
        prepared: list[PreparedProgressNoteExtraction],
    ) -> list[ProgressNoteExtractionOutcome]:
        """Extract notes concurrently on the caller's async event loop."""
        started_at = time.perf_counter()
        if not prepared:
            return []
        concurrency = min(self.concurrency, len(prepared))
        semaphore = asyncio.Semaphore(concurrency)
        outcomes = list(
            await asyncio.gather(
                *(
                    self._extract_prepared_note_isolated(item, semaphore)
                    for item in prepared
                ),
            ),
        )
        for outcome in outcomes:
            if isinstance(outcome.error, asyncio.CancelledError):
                raise outcome.error
            if outcome.error is not None:
                logger.error(
                    "Progress-note AI extraction failed on page %s",
                    outcome.prepared.note.source_page,
                    exc_info=(
                        type(outcome.error),
                        outcome.error,
                        outcome.error.__traceback__,
                    ),
                )

        logger.info(
            "Progress-note AI extraction completed: notes=%s concurrency=%s "
            "duration_seconds=%.3f failures=%s",
            len(prepared),
            concurrency,
            time.perf_counter() - started_at,
            len([outcome for outcome in outcomes if outcome.error is not None]),
        )
        return outcomes

    async def _extract_prepared_note_isolated(
        self,
        prepared: PreparedProgressNoteExtraction,
        semaphore: asyncio.Semaphore,
    ) -> ProgressNoteExtractionOutcome:
        """Bound one extraction and isolate its provider failure."""
        async with semaphore:
            try:
                facts = await self._extract_prepared_note(prepared)
            except asyncio.CancelledError:
                raise
            except Exception as error:  # noqa: BLE001 - isolate one note failure
                return ProgressNoteExtractionOutcome(prepared=prepared, error=error)
            return ProgressNoteExtractionOutcome(prepared=prepared, facts=facts)

    async def _extract_prepared_note(
        self,
        prepared: PreparedProgressNoteExtraction,
    ) -> list[ExtractedFactCreate]:
        """Extract one note without accessing a persistence repository."""
        note = prepared.note
        extracted_clinical_facts = await self._run_data_extraction_agent(
            ExtractionInput(
                text=note.note_text,
                document_filename=self.path.name,
                note_date=note.note_date,
            ),
        )
        logger.debug("Extracted AI facts from note: %s", note)
        return [
            self._build_fact_create(
                note,
                ai_fact,
                person_id=prepared.person_id,
                progress_note_id=prepared.progress_note_id,
            )
            for ai_fact in extracted_clinical_facts.facts
        ]

    def _build_fact_from_ai_output(
        self,
        note: ParsedProgressNote,
        progress_note: PersonProgressNote,
        ai_fact: AIExtractedClinicalFact,
    ) -> ExtractedFactCreate:
        """Build a fact from a progress-note model for compatibility callers."""
        return self._build_fact_create(
            note,
            ai_fact,
            person_id=progress_note.person_id,
            progress_note_id=progress_note.id,
        )

    @staticmethod
    def _build_fact_create(
        note: ParsedProgressNote,
        ai_fact: AIExtractedClinicalFact,
        *,
        person_id: int | None,
        progress_note_id: int | None,
    ) -> ExtractedFactCreate:
        """Build the transient fact returned by a session-free worker."""
        logger.debug("AI Fact: %s", ai_fact)
        payload = ai_fact.payload
        if (
            hasattr(payload, "observed_at")
            and payload.observed_at is None
            and note.note_date is not None
        ):
            payload = payload.model_copy(update={"observed_at": note.note_date})
        return ExtractedFactCreate(
            payload=payload,
            confidence=ai_fact.confidence,
            confidence_reason=ai_fact.confidence_reason,
            model_name=DATA_EXTRACTION_MODEL,
            extraction_method=ExtractionMethod.AI,
            person_id=person_id,
            progress_note_id=progress_note_id,
            source_person_identifier=note.source_person_identifier,
            source_person_name=note.source_person_name,
            facility_name=note.facility_name,
            date_of_birth=note.date_of_birth if person_id is None else None,
            sex=note.sex if person_id is None else None,
            height_in=note.height_in if person_id is None else None,
            source_page=note.source_page,
            source_system="pointclickcare",
        )

    @classmethod
    def deduplicate_notes(
        cls,
        notes: list[ParsedProgressNote],
    ) -> list[tuple[str, ParsedProgressNote]]:
        """Return the first filtered note for each stable progress-note key."""
        unique_notes: dict[str, ParsedProgressNote] = {}
        for note in notes:
            note_key = cls.get_note_key(
                source_person_identifier=note.source_person_identifier,
                effective_at=note.note_date,
                note_type=note.note_type,
                author=note.author,
                note_text=note.note_text,
            )
            unique_notes.setdefault(note_key, note)
        duplicate_count = len(notes) - len(unique_notes)
        if duplicate_count:
            logger.info(
                "Removed %s duplicate progress notes before AI extraction",
                duplicate_count,
            )
        return list(unique_notes.items())

    def extract_notes(self) -> list[ParsedProgressNote]:
        """Return parsed notes whose configured action sends them to the AI."""
        notes = self._parse_report_notes()
        result = [
            note
            for note in notes
            if self._decide_note_action(note) is ProgressNoteAction.SEND_TO_AI
        ]
        logger.debug(
            "%s of %s progress notes eligible for AI extraction",
            len(result),
            len(notes),
        )
        return result

    def extract_nutrition_notes(self) -> list[ParsedProgressNote]:
        """Parse only notes authored as nutrition or dietetics documentation."""
        notes = self._parse_report_notes()
        result = [
            note
            for note in notes
            if any(
                term in " ".join((note.note_type or "").casefold().split())
                for term in _NUTRITION_ASSESSMENT_TYPE_TERMS
            )
        ]
        logger.debug("%s nutrition notes eligible for import", len(result))
        return result

    def _parse_report_notes(
        self,
        *,
        require_identity: bool = True,
    ) -> list[ParsedProgressNote]:
        """Parse every note in the report and validate person identity."""
        notes = self._split_progress_notes(self._extract_document())
        missing_person = (
            next(
                (note for note in notes if note.source_person_identifier is None),
                None,
            )
            if require_identity
            else None
        )
        if missing_person is not None:
            msg = (
                "Unable to determine the person for a progress note beginning "
                f"on page {missing_person.page_start} of {self.path.name}"
            )
            raise ValueError(msg)
        parsed_notes = [self._parse_note(note) for note in notes]
        self._last_parsed_notes = parsed_notes
        return parsed_notes

    @staticmethod
    def _decide_note_action(note: ParsedProgressNote) -> ProgressNoteAction:
        """Filter configured note types and send unknown types to the AI."""
        note_type = " ".join((note.note_type or "").casefold().split())
        if note_type in _ALWAYS_EXTRACT_NOTE_TYPES:
            return ProgressNoteAction.SEND_TO_AI
        explicitly_filtered = (
            note_type in _NUTRITION_FILTERED_NOTE_TYPES
            or note_type.startswith("nursing")
        )
        if explicitly_filtered:
            if _NUTRITION_TERM_RE.search(
                note.note_text,
            ) or _CRITICAL_CLINICAL_EVENT_RE.search(note.note_text):
                return ProgressNoteAction.SEND_TO_AI
            return ProgressNoteAction.FILTER
        return ProgressNoteAction.SEND_TO_AI

    def _extract_document(self) -> list[ExtractedNote]:
        extracted_pages: list[ExtractedNote] = []
        facility_resident_identifier: str | None = None
        source_person_name: str | None = None
        facility_name: str | None = None
        date_of_birth: date | None = None
        sex: str | None = None
        report_observed_at: datetime | None = None
        allergies: tuple[str, ...] = ()
        no_known_allergies = False
        diagnoses: tuple[ParsedHeaderDiagnosis, ...] = ()
        with pymupdf.open(self.path) as document:
            for page_index in range(document.page_count):
                page = document.load_page(page_index)
                lines = self._page_lines(page)
                raw_page_text = page.get_text("text")
                parsed_person = self._parse_person(raw_page_text)
                medical_record_identifier = self._parse_medical_record_identifier(
                    raw_page_text,
                )
                if parsed_person is not None:
                    header_identifier, source_person_name = parsed_person
                    if (
                        medical_record_identifier is not None
                        and header_identifier != medical_record_identifier
                    ):
                        msg = (
                            "Resident header identifier does not match Medical Record "
                            f"# on page {page_index + 1} of {self.path.name}"
                        )
                        raise ValueError(msg)
                    facility_resident_identifier = (
                        medical_record_identifier or header_identifier
                    )
                    date_of_birth = self._parse_date_of_birth(raw_page_text)
                    sex = self._parse_sex(raw_page_text)
                else:
                    facility_resident_identifier = (
                        medical_record_identifier or facility_resident_identifier
                    )
                    date_of_birth = (
                        self._parse_date_of_birth(raw_page_text) or date_of_birth
                    )
                    sex = self._parse_sex(raw_page_text) or sex
                report_observed_at = (
                    self._parse_report_date(raw_page_text) or report_observed_at
                )
                parsed_allergies, parsed_no_known_allergies = self._parse_allergies(
                    raw_page_text,
                )
                if parsed_allergies or parsed_no_known_allergies:
                    allergies = parsed_allergies
                    no_known_allergies = parsed_no_known_allergies
                parsed_diagnoses = self._parse_diagnoses(raw_page_text)
                if parsed_diagnoses:
                    diagnoses = parsed_diagnoses
                facility_name = (
                    self._parse_facility_name(
                        raw_page_text,
                        "Progress Notes *NEW*",
                    )
                    or facility_name
                )
                body_start = self._body_start_index(lines)
                body_text = "\n".join(
                    str(line["text"]) for line in lines[body_start:]
                ).strip()
                if body_text:
                    extracted_pages.append(
                        ExtractedNote(
                            raw_text=body_text,
                            page_start=page_index + 1,
                            page_end=page_index + 1,
                            source_person_identifier=facility_resident_identifier,
                            source_person_name=source_person_name,
                            facility_name=facility_name,
                            date_of_birth=date_of_birth,
                            sex=sex,
                            report_observed_at=report_observed_at,
                            allergies=allergies,
                            no_known_allergies=no_known_allergies,
                            diagnoses=diagnoses,
                        ),
                    )
        return extracted_pages

    @staticmethod
    def _page_lines(page: pymupdf.Page) -> list[dict[str, float | str]]:
        grouped_words: list[list[Word]] = []
        line_tops: list[float] = []
        words = page.get_text("words", sort=True)
        for word in sorted(words, key=lambda item: (item[1], item[0])):
            y0 = float(word[1])
            if line_tops and abs(line_tops[-1] - y0) <= _LINE_Y_TOLERANCE:
                grouped_words[-1].append(word)
            else:
                grouped_words.append([word])
                line_tops.append(y0)

        return [
            {
                "top": min(float(word[1]) for word in line),
                "bottom": max(float(word[3]) for word in line),
                "text": " ".join(
                    str(word[4]) for word in sorted(line, key=lambda item: item[0])
                ),
            }
            for line in grouped_words
        ]

    @staticmethod
    def _body_start_index(lines: list[dict[str, float | str]]) -> int:
        diagnoses_index = next(
            (
                index
                for index, line in enumerate(lines)
                if "diagnoses" in str(line["text"]).casefold()
            ),
            None,
        )
        if diagnoses_index is not None:
            current_bottom = float(lines[diagnoses_index]["bottom"])
            for index in range(diagnoses_index + 1, len(lines)):
                next_top = float(lines[index]["top"])
                if next_top - current_bottom > _HEADER_GAP_THRESHOLD:
                    return index
                current_bottom = float(lines[index]["bottom"])
        return next(
            (
                index
                for index, line in enumerate(lines)
                if _EFFECTIVE_DATE_RE.match(str(line["text"]))
            ),
            len(lines),
        )

    def _parse_note(self, split_note: ExtractedNote) -> ParsedProgressNote:
        """Normalize one extracted note into the declared ProgressNote fields."""
        effective_date = _EFFECTIVE_DATE_RE.search(split_note.raw_text)
        author = _AUTHOR_LINE_RE.search(split_note.raw_text)
        note_type = _NOTE_TYPE_RE.search(split_note.raw_text)
        note_text = _NOTE_TEXT_RE.search(split_note.raw_text)
        parsed_note_text = (
            note_text.group("text").strip()
            if note_text
            else split_note.raw_text.strip()
        )
        return ParsedProgressNote(
            source_person_identifier=split_note.source_person_identifier,
            source_person_name=split_note.source_person_name,
            facility_name=split_note.facility_name,
            date_of_birth=split_note.date_of_birth,
            sex=split_note.sex,
            height_in=split_note.height_in,
            report_observed_at=split_note.report_observed_at,
            allergies=split_note.allergies,
            no_known_allergies=split_note.no_known_allergies,
            diagnoses=split_note.diagnoses,
            source_page=split_note.page_start,
            note_date=(
                self._date_at_midnight(effective_date.group("date"))
                if effective_date
                else None
            ),
            note_type=note_type.group("type").strip() if note_type else None,
            author=author.group("author").strip() if author else None,
            note_text=clean_note_text(parsed_note_text),
            raw_text=split_note.raw_text,
            source_filename=str(self.path),
        )

    @staticmethod
    def _split_progress_notes(pages: list[ExtractedNote]) -> list[ExtractedNote]:
        notes: list[ExtractedNote] = []
        current_lines: list[str] = []
        facility_resident_identifier: str | None = None
        source_person_name: str | None = None
        facility_name: str | None = None
        date_of_birth: date | None = None
        sex: str | None = None
        height_in: float | None = None
        report_observed_at: datetime | None = None
        allergies: tuple[str, ...] = ()
        no_known_allergies = False
        diagnoses: tuple[ParsedHeaderDiagnosis, ...] = ()
        page_start: int | None = None
        page_end: int | None = None

        def append_current_note() -> None:
            nonlocal current_lines, page_start, page_end
            if not current_lines or page_start is None:
                return
            notes.append(
                ExtractedNote(
                    raw_text="\n".join(current_lines).strip(),
                    page_start=page_start,
                    page_end=page_end or page_start,
                    source_person_identifier=facility_resident_identifier,
                    source_person_name=source_person_name,
                    facility_name=facility_name,
                    date_of_birth=date_of_birth,
                    sex=sex,
                    height_in=height_in,
                    report_observed_at=report_observed_at,
                    allergies=allergies,
                    no_known_allergies=no_known_allergies,
                    diagnoses=diagnoses,
                ),
            )
            current_lines = []
            page_start = None
            page_end = None

        for page in pages:
            if (
                current_lines
                and page.source_person_identifier != facility_resident_identifier
                and page.source_person_identifier is not None
            ):
                append_current_note()
            for line in page.raw_text.splitlines():
                if _EFFECTIVE_DATE_RE.match(line):
                    append_current_note()
                    current_lines = [line]
                    page_start = page.page_start
                    facility_resident_identifier = page.source_person_identifier
                    source_person_name = page.source_person_name
                    facility_name = page.facility_name
                    date_of_birth = page.date_of_birth
                    sex = page.sex
                    height_in = page.height_in
                    report_observed_at = page.report_observed_at
                    allergies = page.allergies
                    no_known_allergies = page.no_known_allergies
                    diagnoses = page.diagnoses
                elif current_lines:
                    current_lines.append(line)
                if current_lines:
                    page_end = page.page_end
        append_current_note()
        return notes

    @staticmethod
    def _parse_facility_resident_identifier(text: str) -> str | None:
        person = PccProgressNotesExtractor._parse_person(text)
        return person[0] if person else None

    @staticmethod
    def _parse_person(text: str) -> tuple[str, str] | None:
        match = _PERSON_ID_RE.search(text)
        if match is None:
            return None
        return match.group("id").strip(), match.group("name").strip()

    @staticmethod
    def _parse_medical_record_identifier(text: str) -> str | None:
        match = _MEDICAL_RECORD_RE.search(text)
        return match.group("id").strip() if match is not None else None

    @staticmethod
    def _parse_date_of_birth(text: str) -> date | None:
        match = _DOB_RE.search(text)
        if match is None:
            return None
        month, day, year = (int(part) for part in match.group("date").split("/"))
        return date(year, month, day)

    @staticmethod
    def _parse_sex(text: str) -> str | None:
        match = _SEX_RE.search(text)
        if match is None:
            return None
        return match.group("sex").casefold()[0]

    @staticmethod
    def _parse_report_date(text: str) -> datetime | None:
        match = _REPORT_DATE_RE.search(text)
        if match is None:
            return None
        value = match.group("date")
        for date_format in ("%b %d, %Y", "%B %d, %Y", "%m/%d/%Y"):
            try:
                return datetime.strptime(value, date_format).replace(tzinfo=UTC)
            except ValueError:
                continue
        return None

    @classmethod
    def _parse_allergies(cls, text: str) -> tuple[tuple[str, ...], bool]:
        match = _ALLERGIES_BLOCK_RE.search(text)
        if match is None:
            return (), False
        value = re.sub(r"\s+", " ", match.group("value")).strip(" ,")
        if cls._normalize_text(value) in _NO_KNOWN_ALLERGIES:
            return (), True
        allergens = tuple(
            dict.fromkeys(item.strip() for item in value.split(",") if item.strip()),
        )
        return allergens, False

    @staticmethod
    def _parse_diagnoses(text: str) -> tuple[ParsedHeaderDiagnosis, ...]:
        match = _DIAGNOSES_BLOCK_RE.search(text)
        if match is None:
            return ()
        value = re.sub(r"\s+", " ", match.group("value")).strip(" ,")
        diagnoses: list[ParsedHeaderDiagnosis] = []
        seen_codes: set[str] = set()
        for diagnosis_match in _DIAGNOSIS_RE.finditer(value):
            diagnosis = diagnosis_match.group("diagnosis").strip(" ,")
            code = diagnosis_match.group("code").strip()
            if not diagnosis or code in seen_codes:
                continue
            seen_codes.add(code)
            diagnoses.append(ParsedHeaderDiagnosis(diagnosis=diagnosis, code=code))
        return tuple(diagnoses)

    @staticmethod
    def _date_at_midnight(value: str) -> datetime:
        month, day, year = (int(part) for part in value.split("/"))
        return datetime(year, month, day, tzinfo=UTC)

    async def _run_data_extraction_agent(
        self,
        extraction_input: ExtractionInput,
    ) -> ExtractedClinicalFacts:
        """Run the agent and enforce its transient-fact result contract."""
        data_extraction_agent = DataExtractionAgent()
        return await data_extraction_agent.run(extraction_input)

    @staticmethod
    def get_note_key(
        source_person_identifier: str | None,
        effective_at: datetime | None,
        note_type: str | None,
        author: str | None,
        note_text: str,
    ) -> str:
        """Get unique note key for current progress note."""
        value = "|".join(
            [
                (source_person_identifier or "").strip(),
                effective_at.isoformat() if effective_at is not None else "",
                PccProgressNotesExtractor._normalize_text(note_type or ""),
                PccProgressNotesExtractor._normalize_text(author or ""),
                PccProgressNotesExtractor._normalize_text(note_text),
            ],
        )
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    @staticmethod
    def _normalize_text(value: str) -> str:
        value = unicodedata.normalize("NFKC", value)
        value = re.sub(r"\s+", " ", value)
        return value.strip().lower()
