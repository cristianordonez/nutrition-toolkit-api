from __future__ import annotations

import re
from datetime import UTC, date, datetime

import pymupdf

from ntk.models.extracted_fact_create import ExtractedFactCreate, WeightPayload

from .base import PersonExtractor
from .registry import register_extractor

_WEIGHT_LINE_RE = re.compile(
    r"^(?P<date>\d{1,2}/\d{1,2}/\d{4})\s+"
    r"(?P<time>\d{1,2}:\d{2})\s+"
    r"(?P<weight>\d+(?:\.\d+)?)\s+"
    r"Lbs\s*"
    r"(?:\((?P<description>[^)]*)\))?",
    flags=re.IGNORECASE | re.MULTILINE,
)
_PERSON_RE = re.compile(
    r"Resident\s*:\s*(?P<name>.+?)\s*\((?P<id>[A-Z]{0,4}\d+)\)",
    flags=re.IGNORECASE,
)
_PERSON_ROW_RE = re.compile(
    r"^\s*(?P<name>.+?)\s+\(\s*(?P<id>[A-Z]{0,4}\d+)\s*\)\s+"
    r"Location\s*:",
    flags=re.IGNORECASE,
)
_ALL_PERSONS_RE = re.compile(
    r"^\s*Resident\s*:\s*All\b",
    flags=re.IGNORECASE | re.MULTILINE,
)
_HEIGHT_RE = re.compile(
    r"\bHeight\s*:\s*(?P<height>\d+(?:\.\d+)?)\s+Inches\b",
    flags=re.IGNORECASE,
)
_ADMISSION_DATE_RE = re.compile(
    r"\b(?:DOA|(?:Admit|Admission) Date)\s*:\s*"
    r"(?P<date>\d{1,2}/\d{1,2}/\d{4})\b",
    flags=re.IGNORECASE,
)

WeightRowKey = tuple[datetime, float, str | None]
WeightKey = tuple[str | None, datetime]
PersonWeight = tuple[int, str | None, str | None, float | None, WeightPayload]


@register_extractor
class PccWeightHistoryExtractor(PersonExtractor):
    """Recognize and extract a PCC weight history report."""

    def is_expected_format(self) -> bool:
        """Return whether the document is a PCC weight history report."""
        return self._is_pdf(self.path) and self._first_page_contains(
            "Weights and Vitals Summary",
        )

    async def extract(self) -> list[ExtractedFactCreate]:
        """Extract each weight row as a transient fact."""
        return self._facts(require_identity=True)

    async def extract_for_demo(self) -> list[ExtractedFactCreate]:
        """Extract weights without requiring a persistable person identity."""
        return self._facts(require_identity=False)

    def _facts(self, *, require_identity: bool) -> list[ExtractedFactCreate]:
        """Build facts using strict ingestion or relaxed demo identity rules."""
        facility_name = self._parse_facility_name(
            self._first_page_text,
            "Weights and Vitals Summary",
        )
        return [
            self._build_extracted_fact(
                weight,
                source_person_identifier=facility_resident_identifier,
                source_person_name=source_person_name,
                facility_name=facility_name,
                height_in=height_in,
                source_page=source_page,
                source_system="pointclickcare",
            )
            for (
                source_page,
                facility_resident_identifier,
                source_person_name,
                height_in,
                weight,
            ) in self._extract_pdf(require_identity=require_identity)
        ]

    def _extract_pdf(self, *, require_identity: bool = True) -> list[PersonWeight]:
        is_all_persons = bool(
            _ALL_PERSONS_RE.search(self._first_page_text),
        )
        if is_all_persons:
            return self._extract_all_persons_pdf()
        return self._extract_single_person_pdf(require_identity=require_identity)

    def _extract_single_person_pdf(
        self,
        *,
        require_identity: bool = True,
    ) -> list[PersonWeight]:
        """Extract the existing single-person report format."""
        entries: list[PersonWeight] = []
        seen: set[WeightKey] = set()
        facility_resident_identifier: str | None = None
        source_person_name: str | None = None
        height_in: float | None = None
        with pymupdf.open(self.path) as document:
            for page_number in range(document.page_count):
                page = document.load_page(page_number)
                page_text = page.get_text("text")
                parsed_person = self._parse_person(page_text)
                if parsed_person is not None:
                    facility_resident_identifier, source_person_name = parsed_person
                    height_in = self._parse_height(page_text)
                else:
                    height_in = self._parse_height(page_text) or height_in
                weight_rows = self._parse_weight_rows(page_text)
                if (
                    require_identity
                    and weight_rows
                    and facility_resident_identifier is None
                ):
                    msg = (
                        "Unable to determine the person for weight rows on "
                        f"page {page_number + 1} of {self.path.name}"
                    )
                    raise ValueError(msg)
                for weight_key, entry in weight_rows:
                    key = (facility_resident_identifier, weight_key[0])
                    if key in seen:
                        continue
                    seen.add(key)
                    entries.append(
                        (
                            page_number + 1,
                            facility_resident_identifier,
                            source_person_name,
                            height_in,
                            entry,
                        ),
                    )
        return entries

    def _extract_all_persons_pdf(self) -> list[PersonWeight]:
        """Parse an all-persons report while preserving cross-page state."""
        entries: list[PersonWeight] = []
        seen: set[WeightKey] = set()
        current_person: tuple[str, str] | None = None
        current_section: str | None = None
        height_in: float | None = None
        with pymupdf.open(self.path) as document:
            for page_number in range(document.page_count):
                page_text = document.load_page(page_number).get_text("text")
                for line in page_text.splitlines():
                    parsed_person = self._parse_person_row(line)
                    if parsed_person is not None:
                        current_person = parsed_person
                        current_section = None
                        height_in = self._parse_height(line)
                        continue
                    normalized_line = " ".join(line.split()).casefold()
                    if normalized_line == "height summary":
                        current_section = "height"
                        continue
                    if normalized_line == "weight summary":
                        current_section = "weight"
                        continue
                    if current_person is None or current_section != "weight":
                        continue
                    for weight_key, entry in self._parse_weight_rows(line):
                        (
                            facility_resident_identifier,
                            source_person_name,
                        ) = current_person
                        key = (facility_resident_identifier, weight_key[0])
                        if key in seen:
                            continue
                        seen.add(key)
                        entries.append(
                            (
                                page_number + 1,
                                facility_resident_identifier,
                                source_person_name,
                                height_in,
                                entry,
                            ),
                        )
        return entries

    @classmethod
    def _parse_weight_summary(cls, text: str) -> list[WeightPayload]:
        """Parse dated pound measurements while ignoring other vital rows."""
        return [entry for _, entry in cls._parse_weight_rows(text)]

    @staticmethod
    def _parse_weight_rows(text: str) -> list[tuple[WeightRowKey, WeightPayload]]:
        rows: list[tuple[WeightRowKey, WeightPayload]] = []
        for match in _WEIGHT_LINE_RE.finditer(text):
            month, day, year = (int(part) for part in match.group("date").split("/"))
            hour, minute = (int(part) for part in match.group("time").split(":"))
            measured_at = datetime(year, month, day, hour, minute, tzinfo=UTC)
            weight = float(match.group("weight"))
            raw_description = match.group("description")
            description = raw_description.strip() if raw_description else None
            entry = WeightPayload(
                measured_at=measured_at,
                weight_lb=weight,
                description=description,
            )
            key = (measured_at, weight, description)
            rows.append((key, entry))
        return rows

    @staticmethod
    def _parse_facility_resident_identifier(text: str) -> str | None:
        person = PccWeightHistoryExtractor._parse_person(text)
        return person[0] if person else None

    @staticmethod
    def _parse_person(text: str) -> tuple[str, str] | None:
        match = _PERSON_RE.search(text)
        if match is None:
            return None
        return match.group("id").strip(), match.group("name").strip()

    @staticmethod
    def _parse_person_row(text: str) -> tuple[str, str] | None:
        """Return identity from an all-persons body row."""
        match = _PERSON_ROW_RE.search(text)
        if match is None:
            return None
        return match.group("id").strip(), " ".join(match.group("name").split())

    @staticmethod
    def _parse_height(text: str) -> float | None:
        match = _HEIGHT_RE.search(text)
        return float(match.group("height")) if match else None

    @staticmethod
    def _parse_admission_date(text: str) -> date | None:
        match = _ADMISSION_DATE_RE.search(text)
        if match is None:
            return None
        month, day, year = (int(part) for part in match.group("date").split("/"))
        return date(year, month, day)
