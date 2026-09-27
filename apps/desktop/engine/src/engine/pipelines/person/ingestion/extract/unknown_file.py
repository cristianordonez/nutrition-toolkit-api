"""Text extraction for documents without a deterministic extractor."""

from __future__ import annotations

import asyncio
import logging
import re
import typing
from datetime import UTC, datetime, time

import pymupdf

from engine.agents.data_extraction_agent import (
    DATA_EXTRACTION_MODEL,
    DataExtractionAgent,
    ExtractionInput,
)
from engine.models.extracted_fact_create import ExtractedFactCreate
from engine.models.sql.clinical_fact import ExtractionMethod
from engine.utils.tokens import sliding_window

from .base import PersonExtractor

if typing.TYPE_CHECKING:
    import pathlib
    from datetime import date

    from engine.models.ai_extraction import AIUnknownDocumentFact


#: The desktop app offers these for drag-and-drop, so the extractor has to
#: accept the same set. A plain-text file has no pages, which is why page
#: provenance below is optional rather than assumed.
_SUPPORTED_SUFFIXES = {".pdf", ".txt"}
_PLAIN_TEXT_SUFFIXES = {".txt"}
_UNKNOWN_DOCUMENT_CHUNK_TOKENS = 600
_MAX_UNKNOWN_FILE_SIZE_BYTES = 10 * 1024 * 1024

# Matches common EHR date-of-record labels so an otherwise-undated chunk can
# still receive a best-guess `note_date` for the extraction agent to use as
# `observed_at`. The first match on a page wins.
_NOTE_DATE_PATTERN = re.compile(
    r"(?:date of service|filed|result date|service date|visit date|"
    r"date/time of service|admission date/?time)\s*:?\s*"
    r"(\d{1,2}/\d{1,2}/\d{2,4})(?:\s+(\d{1,2}:\d{2}))?",
    re.IGNORECASE,
)
_NOTE_DATE_FORMATS = ("%m/%d/%Y", "%m/%d/%y")

logger = logging.getLogger(__name__)


class UnknownFileTooLargeError(ValueError):
    """Raised before extraction when an unknown file exceeds the size limit."""


class UnknownFileUnsupportedFormatError(TypeError):
    """Raised before extraction when unknown file is unsupported format."""


class UnknownFileExtractor(PersonExtractor):
    """Read text from an unrecognized file of a supported file type."""

    def __init__(
        self,
        file: pathlib.Path,
        *,
        max_file_size_bytes: int = _MAX_UNKNOWN_FILE_SIZE_BYTES,
        extraction_agent: DataExtractionAgent | None = None,
    ) -> None:
        """Store the document to read.

        ``extraction_agent`` lets a caller supply an agent bound to a specific
        provider, which is how the same document can be run through more than
        one model for comparison.
        """
        super().__init__(file)
        if max_file_size_bytes <= 0:
            msg = "Unknown file size limit must be greater than zero"
            raise ValueError(msg)
        self.file = file
        self.max_file_size_bytes = max_file_size_bytes
        self._extraction_agent = extraction_agent
        self._validate_file_size()
        self._validate_file_type()

    def is_expected_format(self) -> bool:
        """Return true when file is supported for extraction."""
        self._validate_file_size()
        self._validate_file_type()
        return True

    async def extract(
        self,
        *,
        person_id: int | None = None,
        known_person_name: str | None = None,
        known_date_of_birth: date | None = None,
    ) -> list[ExtractedFactCreate]:
        """Parse unstructured text using an extraction agent.

        `person_id`, `known_person_name`, and `known_date_of_birth` are supplied
        by a caller that already knows which resident this document belongs to
        (for example, a person-scoped upload). They resolve identity ambiguity
        that the document text alone cannot: `known_person_name`/
        `known_date_of_birth` help the agent decide which passages of a
        multi-person document belong to that resident, and `person_id`, when
        given, is stamped directly onto every resulting fact so downstream
        persistence skips name/DOB matching entirely.
        """
        facts: list[ExtractedFactCreate] = []
        for source_page, page_text in self._get_document_pages():
            note_date = self._detect_note_date(page_text)
            for chunk in sliding_window(
                page_text,
                chunk_size=_UNKNOWN_DOCUMENT_CHUNK_TOKENS,
                overlap=25,
            ):
                if not chunk.strip():
                    continue
                try:
                    extracted_facts = await self._run_data_extraction_agent(
                        ExtractionInput(
                            text=chunk,
                            document_filename=self.file.name,
                            note_date=note_date,
                            known_person_name=known_person_name,
                            known_date_of_birth=known_date_of_birth,
                        ),
                    )
                except asyncio.CancelledError:
                    raise
                except Exception:  # isolate one chunk's failure
                    logger.exception(
                        "Unknown-document AI extraction failed for %s page %s; "
                        "skipping this chunk",
                        self.file.name,
                        source_page,
                    )
                    continue
                facts.extend(
                    self._build_extracted_fact_create(
                        fact,
                        source_page,
                        person_id=person_id,
                    )
                    for fact in extracted_facts
                )
        return self._attribute_to_document_subject(facts, self.file.name)

    @staticmethod
    def _attribute_to_document_subject(
        facts: list[ExtractedFactCreate],
        document_name: str,
    ) -> list[ExtractedFactCreate]:
        """Complete each fact's identity from the one the document establishes.

        Chunk boundaries are an artifact of tokenization, not a change of
        subject. A discharge packet identifies its patient in a header, but a
        600-token window taken from the middle of a medication table contains
        no header -- so the agent reads real facts out of it and has nothing
        to attribute them to. Persistence then refuses the whole batch,
        because a person cannot be created from facts alone.

        Identity arrives in pieces, not all-or-nothing: one chunk carries a
        name and an MRN, the next a name and a date of birth, a third only a
        name. So this fills in each *field* a fact is missing rather than only
        rescuing facts that named nobody at all -- a chunk that has the name
        but no birth date and no identifier is rejected by persistence just as
        surely as one with no identity whatsoever.

        Applied only when the document speaks about one person. Two facts that
        state the same field differently mean the document names more than one
        subject, and guessing which of them an unattributed medication belongs
        to is exactly the kind of error that must not be made quietly: nothing
        is filled in, and persistence fails loudly instead.
        """
        subject = _document_subject(facts)
        if not isinstance(subject, _DocumentSubject):
            # Downstream this surfaces as "Cannot create a person without
            # first name, last name, and birth date or a person identifier",
            # thrown from persistence with no hint of which document or which
            # names caused it. Say so here, where that is still known.
            incomplete = sum(1 for fact in facts if not _is_persistable(fact))
            if incomplete and subject:
                logger.warning(
                    "%s identifies more than one subject (%s), so %s of %s facts "
                    "keep an incomplete identity and will be rejected",
                    document_name,
                    "; ".join(conflict.describe() for conflict in subject),
                    incomplete,
                    len(facts),
                )
            return facts
        for fact in facts:
            fact.source_person_name = fact.source_person_name or subject.name
            fact.source_person_identifier = (
                fact.source_person_identifier or subject.identifier
            )
            fact.date_of_birth = fact.date_of_birth or subject.birth_date
        return facts

    def _validate_file_size(self) -> None:
        """Reject oversized files before reading content or calling the agent."""
        file_size = self.file.stat().st_size
        if file_size <= self.max_file_size_bytes:
            return
        max_size_mib = self.max_file_size_bytes / (1024 * 1024)
        actual_size_mib = file_size / (1024 * 1024)
        msg = (
            f"Unknown file '{self.file.name}' is too large for AI extraction "
            f"({actual_size_mib:.2f} MiB); maximum size is {max_size_mib:.2f} MiB"
        )
        raise UnknownFileTooLargeError(msg)

    def _validate_file_type(self) -> None:
        suffix = self.file.suffix.casefold()
        if suffix not in _SUPPORTED_SUFFIXES:
            msg = f"Unsupported file type for text extraction: {suffix or '<none>'}"
            raise UnknownFileUnsupportedFormatError(msg)

    async def _run_data_extraction_agent(
        self,
        extraction_input: ExtractionInput,
    ) -> list[AIUnknownDocumentFact]:
        """Run the agent and enforce its transient-fact result contract."""
        agent = self._extraction_agent or DataExtractionAgent()
        return await agent.run_unknown_document(extraction_input)

    def _build_extracted_fact_create(
        self,
        extracted: AIUnknownDocumentFact,
        source_page: int | None,
        *,
        person_id: int | None = None,
    ) -> ExtractedFactCreate:
        """Convert an AI fact while preserving its unresolved identity clues."""
        identity = extracted.identity
        return ExtractedFactCreate(
            payload=extracted.fact.payload,
            confidence=extracted.fact.confidence,
            confidence_reason=extracted.fact.confidence_reason,
            model_name=DATA_EXTRACTION_MODEL,
            extraction_method=ExtractionMethod.AI,
            source_person_identifier=identity.source_person_identifier,
            source_person_name=identity.source_person_name,
            date_of_birth=identity.date_of_birth,
            source_page=source_page,
            person_id=person_id,
        )

    @staticmethod
    def _detect_note_date(text: str) -> datetime | None:
        """Return a best-guess document date from a common EHR date label.

        Used as the extraction agent's `note_date` fallback so a chunk that
        never states its own date can still receive an `observed_at` value.
        """
        match = _NOTE_DATE_PATTERN.search(text)
        if match is None:
            return None
        date_text, time_text = match.group(1), match.group(2)
        parsed_date = None
        for date_format in _NOTE_DATE_FORMATS:
            try:
                parsed_date = datetime.strptime(date_text, date_format).date()  # noqa: DTZ007
            except ValueError:  # noqa: PERF203 - trying each format is the point
                continue
            else:
                break
        if parsed_date is None:
            return None
        parsed_time = time.min
        if time_text:
            try:
                parsed_time = datetime.strptime(time_text, "%H:%M").time()  # noqa: DTZ007
            except ValueError:
                parsed_time = time.min
        return datetime.combine(parsed_date, parsed_time, tzinfo=UTC)

    def _get_document_contents(self) -> str:
        """Return all readable text, retained for callers needing plain text."""
        return "\n".join(text for _, text in self._get_document_pages())

    def _get_document_pages(self) -> list[tuple[int | None, str]]:
        """Read text with one-based PDF page provenance when available."""
        if self.file.suffix.casefold() in _PLAIN_TEXT_SUFFIXES:
            # No pages to cite, so provenance is None rather than a made-up 1.
            text = self.file.read_text(encoding="utf-8", errors="replace")
            return [(None, text.strip())]
        with pymupdf.open(self.file) as document:
            return [
                (page_number + 1, document.load_page(page_number).get_text().strip())
                for page_number in range(document.page_count)
            ]


class _Conflict(typing.NamedTuple):
    """Two facts stated one field differently, with the pair that disagreed.

    Carries the values because "this document names more than one subject" is
    not, on its own, enough to act on: which field split, and into what, is
    the difference between a genuine second patient and two spellings that
    should have compared equal.
    """

    field: str
    first: object
    second: object

    def describe(self) -> str:
        """Render the disagreement for a log line."""
        return f"{self.field} {self.first!r} vs {self.second!r}"


#: Split a name into comparable words, so "Diawatan, Mark" and "Mark Diawatan"
#: are recognised as one person written two ways.
_NAME_WORD_RE = re.compile(r"[a-z0-9]+")


class _DocumentSubject(typing.NamedTuple):
    """The one person a document speaks about, assembled from every chunk."""

    name: str | None
    identifier: str | None
    birth_date: date | None


def _is_persistable(fact: ExtractedFactCreate) -> bool:
    """Whether this fact carries enough identity for a person to be created.

    Mirrors the rule `person_service.resolve_or_create_person` enforces, so
    the warning above counts the facts that will actually be rejected.
    """
    has_natural_identity = bool(fact.source_person_name and fact.date_of_birth)
    return has_natural_identity or bool(fact.source_person_identifier)


def _name_key(name: str | None) -> frozenset[str] | None:
    """Compare names by their word set, ignoring case, order and punctuation."""
    words = frozenset(_NAME_WORD_RE.findall((name or "").casefold()))
    return words or None


def _text_key(value: str | None) -> str | None:
    """Compare identifiers ignoring case and punctuation, so "MR-123" == "mr123"."""
    cleaned = "".join(
        character for character in (value or "").casefold() if character.isalnum()
    )
    return cleaned or None


def _agreed_value[T](
    facts: list[ExtractedFactCreate],
    read: typing.Callable[[ExtractedFactCreate], T | None],
    key: typing.Callable[[T | None], object],
    field: str,
) -> T | _Conflict | None:
    """Return the value every fact that stated this field agreed on.

    None when no fact stated it; a `_Conflict` naming both values when two
    disagreed. The first spelling wins, so the value keeps whatever formatting
    the document used.
    """
    agreed: T | None = None
    agreed_key: object = None
    for fact in facts:
        value = read(fact)
        value_key = key(value)
        if value_key is None:
            continue
        if agreed_key is None:
            agreed, agreed_key = value, value_key
        elif value_key != agreed_key:
            return _Conflict(field=field, first=agreed, second=value)
    return agreed


def _document_subject(
    facts: list[ExtractedFactCreate],
) -> _DocumentSubject | list[_Conflict] | None:
    """Who the document is about, when that is one settled answer.

    Otherwise says why not: a list of `_Conflict` when chunks identified
    different people, or None when no chunk identified anybody. Neither is
    safe to fill in from, but only the first is worth reporting.
    """
    name = _agreed_value(
        facts,
        lambda fact: fact.source_person_name,
        _name_key,
        "name",
    )
    identifier = _agreed_value(
        facts,
        lambda fact: fact.source_person_identifier,
        _text_key,
        "identifier",
    )
    birth_date = _agreed_value(
        facts,
        lambda fact: fact.date_of_birth,
        lambda value: value,
        "date of birth",
    )
    conflicts = [
        value
        for value in (name, identifier, birth_date)
        if isinstance(value, _Conflict)
    ]
    if conflicts:
        return conflicts
    if name is None and identifier is None and birth_date is None:
        return None

    return _DocumentSubject(
        name=typing.cast("str | None", name),
        identifier=typing.cast("str | None", identifier),
        birth_date=typing.cast("date | None", birth_date),
    )


def _or_none[T](value: T | _Conflict | None) -> T | None:
    """Drop a disagreement, keeping only a value every chunk agreed on."""
    return None if isinstance(value, _Conflict) else value
