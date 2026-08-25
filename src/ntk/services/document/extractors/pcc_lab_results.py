from __future__ import annotations

import re
from datetime import UTC, date, datetime, time

import pymupdf

from ntk.models.sql.resident import (
    LabResult,
    PccLabReportExtraction,
    SourceReference,
)

from .base import BaseExtractor
from .registry import register_extractor

_COLLECTION_DATE_RE = re.compile(
    r"\bCollection Date\s*:\s*(?P<date>\d{1,2}/\d{1,2}/\d{4})\b",
    flags=re.IGNORECASE,
)
_ADMISSION_DATE_RE = re.compile(
    r"\b(?:Admit|Admission) Date\s*:\s*(?P<date>\d{1,2}/\d{1,2}/\d{4})\b",
    flags=re.IGNORECASE,
)
_DOB_RE = re.compile(
    r"\bDOB\s*(?P<date>\d{1,2}/\d{1,2}/\d{4})\b",
    flags=re.IGNORECASE,
)
_FACILITY_ID_RE = re.compile(r"\bResident\s*:[^(]+?\((?P<id>[A-Z]{0,4}\d+)\)")
_FINAL_STATUSES = frozenset({"Final", "Corrected", "Preliminary"})
_FLAG_TOKENS = frozenset({"A", "AA", "H", "HH", "L", "LL"})
_VALUE_RE = re.compile(r"^(?:[<>]=?)?\d+(?:\.\d+)?$|^\*$|^Invalid$", re.IGNORECASE)
_IGNORED_LAB_NAMES = frozenset(
    {
        "UNABLE TO OBTAIN",
        "REDRAW NOTE",
        "REDRAW CLOTTED REASON",
        "RESCHEDULE SPECIFIED TEST",
        "EXPIRED CONTAINER REC'D",
    },
)
_IGNORED_RESULTS = frozenset({"*", "invalid", "pending", "see", "see attachment"})
_MIN_RESULT_LINE_TOKENS = 3
_LINE_Y_TOLERANCE = 2.0
_NAME_RESULT_GAP = 10.0

Word = tuple[float, float, float, float, str, int, int, int]


@register_extractor
class PccLabResultsExtractor(BaseExtractor):
    """Recognize and extract a PCC lab results report."""

    def is_expected_format(self) -> bool:
        """Return whether the document is a PCC lab results report."""
        return self._first_page_contains("Lab Results", "Laboratory Results")

    def extract(self) -> PccLabReportExtraction:
        """Extract finalized lab-result rows and resident metadata."""
        document_text, lab_results = self._extract_pdf()
        date_of_birth = self._parse_date(document_text, _DOB_RE)
        return PccLabReportExtraction(
            facility_id=self._parse_facility_id(document_text),
            admission_date=self._parse_date(document_text, _ADMISSION_DATE_RE),
            age=self._calculate_age(date_of_birth),
            lab_results=lab_results,
            source=SourceReference(
                source=str(self.path),
                source_type="PCC Lab Results Report",
                extracted_at=datetime.now(tz=UTC),
            ),
        )

    def _extract_pdf(self) -> tuple[str, list[LabResult]]:
        page_texts: list[str] = []
        results: list[LabResult] = []
        current_date: date | None = None
        with pymupdf.open(self.path) as document:
            for page_number in range(document.page_count):
                page = document.load_page(page_number)
                page_text = page.get_text().strip()
                page_texts.append(page_text)
                current_date = self._parse_collection_date(page_text) or current_date
                if current_date is not None:
                    results.extend(self._parse_page_words(page, current_date))
        return "\n".join(page_texts), self._deduplicate(results)

    @classmethod
    def _parse_page_words(
        cls,
        page: pymupdf.Page,
        collection_date: date,
    ) -> list[LabResult]:
        lines = cls._group_words(page.get_text("words", sort=True))
        header_index, boundaries = cls._find_result_columns(lines)
        if header_index is None:
            return []
        results = []
        for words in lines[header_index + 1 :]:
            values = cls._assign_to_columns(words, boundaries)
            result = cls._lab_result_from_columns(values, collection_date)
            if result is not None:
                results.append(result)
        return results

    @staticmethod
    def _group_words(words: list[Word]) -> list[list[Word]]:
        lines: list[list[Word]] = []
        line_tops: list[float] = []
        for word in sorted(words, key=lambda item: (item[1], item[0])):
            y0 = float(word[1])
            if line_tops and abs(line_tops[-1] - y0) <= _LINE_Y_TOLERANCE:
                lines[-1].append(word)
            else:
                lines.append([word])
                line_tops.append(y0)
        for line in lines:
            line.sort(key=lambda item: item[0])
        return lines

    @staticmethod
    def _find_result_columns(
        lines: list[list[Word]],
    ) -> tuple[int | None, dict[str, tuple[float, float]]]:
        for index, words in enumerate(lines):
            labels = {word[4].casefold().rstrip(".:"): word for word in words}
            if not {"result", "unit", "ref", "flag", "status"}.issubset(labels):
                continue
            centers = {
                name: (float(labels[label][0]) + float(labels[label][2])) / 2
                for name, label in (
                    ("result", "result"),
                    ("unit", "unit"),
                    ("reference_range", "ref"),
                    ("flag", "flag"),
                    ("status", "status"),
                )
            }
            result_left = float(labels["result"][0]) - _NAME_RESULT_GAP
            result_unit = (centers["result"] + centers["unit"]) / 2
            unit_reference = (centers["unit"] + centers["reference_range"]) / 2
            reference_flag = (centers["reference_range"] + centers["flag"]) / 2
            flag_status = (centers["flag"] + centers["status"]) / 2
            return index, {
                "name": (float("-inf"), result_left),
                "result": (result_left, result_unit),
                "unit": (result_unit, unit_reference),
                "reference_range": (unit_reference, reference_flag),
                "flag": (reference_flag, flag_status),
                "status": (flag_status, float("inf")),
            }
        return None, {}

    @staticmethod
    def _assign_to_columns(
        words: list[Word],
        boundaries: dict[str, tuple[float, float]],
    ) -> dict[str, str]:
        values: dict[str, list[str]] = {name: [] for name in boundaries}
        for word in words:
            midpoint = (float(word[0]) + float(word[2])) / 2
            for name, (left, right) in boundaries.items():
                if left <= midpoint < right:
                    values[name].append(str(word[4]))
                    break
        return {name: " ".join(parts).strip() for name, parts in values.items()}

    @staticmethod
    def _lab_result_from_columns(
        values: dict[str, str],
        collection_date: date,
    ) -> LabResult | None:
        name = values["name"]
        result = values["result"]
        status = values["status"]
        if (
            not name
            or name in _IGNORED_LAB_NAMES
            or status not in _FINAL_STATUSES
            or not result
            or result.casefold() in _IGNORED_RESULTS
        ):
            return None
        return LabResult(
            name=name,
            result=result,
            unit=values["unit"] or None,
            reference_range=values["reference_range"] or None,
            flag=values["flag"] or None,
            date=PccLabResultsExtractor._result_datetime(collection_date),
        )

    @staticmethod
    def _parse_result_line(line: str, collection_date: date) -> LabResult | None:
        tokens = line.strip().split()
        if len(tokens) < _MIN_RESULT_LINE_TOKENS:
            return None
        status_index = next(
            (
                index
                for index in range(len(tokens) - 1, -1, -1)
                if tokens[index] in _FINAL_STATUSES
            ),
            None,
        )
        if status_index is None:
            return None
        flag = (
            tokens[status_index - 1]
            if status_index > 0 and tokens[status_index - 1] in _FLAG_TOKENS
            else None
        )
        data_tokens = tokens[: status_index - 1 if flag else status_index]
        value_index = next(
            (
                index
                for index, token in enumerate(data_tokens)
                if _VALUE_RE.match(token) is not None
            ),
            None,
        )
        if value_index is None:
            return None
        name = " ".join(data_tokens[:value_index]).strip()
        result = data_tokens[value_index]
        if (
            not name
            or name in _IGNORED_LAB_NAMES
            or result.casefold() in _IGNORED_RESULTS
        ):
            return None
        unit, reference_range = PccLabResultsExtractor._parse_unit_and_range(
            data_tokens[value_index + 1 :],
        )
        return LabResult(
            name=name,
            result=result,
            unit=unit,
            reference_range=reference_range,
            date=PccLabResultsExtractor._result_datetime(collection_date),
        )

    @staticmethod
    def _parse_unit_and_range(tokens: list[str]) -> tuple[str | None, str | None]:
        if not tokens:
            return None, None
        if len(tokens) == 1:
            return tokens[0], None
        if tokens[:2] == ["See", "note"]:
            return "See note", " ".join(tokens[2:]) or None
        return tokens[0], " ".join(tokens[1:]) or None

    @staticmethod
    def _deduplicate(results: list[LabResult]) -> list[LabResult]:
        unique: list[LabResult] = []
        seen: set[tuple[datetime | None, str, str | None]] = set()
        for result in results:
            key = (result.date, result.name.casefold(), result.result)
            if key not in seen:
                seen.add(key)
                unique.append(result)
        return unique

    @staticmethod
    def _parse_collection_date(text: str) -> date | None:
        return PccLabResultsExtractor._parse_date(text, _COLLECTION_DATE_RE)

    @staticmethod
    def _parse_date(text: str, pattern: re.Pattern[str]) -> date | None:
        match = pattern.search(text)
        if match is None:
            return None
        month, day, year = (int(part) for part in match.group("date").split("/"))
        return date(year, month, day)

    @staticmethod
    def _result_datetime(collection_date: date) -> datetime:
        return datetime.combine(collection_date, time.min, tzinfo=UTC)

    @staticmethod
    def _calculate_age(date_of_birth: date | None) -> int | None:
        if date_of_birth is None:
            return None
        today = datetime.now(tz=UTC).date()
        return (
            today.year
            - date_of_birth.year
            - ((today.month, today.day) < (date_of_birth.month, date_of_birth.day))
        )

    @staticmethod
    def _parse_facility_id(text: str) -> str | None:
        match = _FACILITY_ID_RE.search(text)
        return match.group("id") if match else None
