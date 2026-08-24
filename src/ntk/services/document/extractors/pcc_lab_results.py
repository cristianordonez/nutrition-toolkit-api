from __future__ import annotations

import re
import typing
from datetime import UTC, date, datetime

import pdfplumber

from ntk.models.resident_data import LabReportExtraction, SourceReference
from ntk.models.sql.resident import LabResult

from .base import BaseExtractor
from .registry import register_extractor

if typing.TYPE_CHECKING:
    from collections.abc import Iterable


_COLLECTION_DATE_RE = re.compile(
    r"\bCollection Date\s*:\s*(?P<date>\d{1,2}/\d{1,2}/\d{4})\b",
    flags=re.IGNORECASE,
)
_FACILITY_ID_RE = re.compile(r"\bResident\s*:[^(]+?\((?P<facility_id>[A-Z]{0,4}\d+)\)")
_STATUS_TOKENS = frozenset({"Final", "Corrected", "Preliminary"})
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
_MIN_RESULT_LINE_TOKENS = 3


@register_extractor
class PccLabResultsExtractor(BaseExtractor):
    """Recognize a PCC lab results report."""

    def is_expected_format(self) -> bool:
        """Return whether the document is a PCC lab results report."""
        return self._first_page_contains("Lab Results", "Laboratory Results")

    def extract(self) -> LabReportExtraction:
        """Extract latest completed lab results from a PCC lab report."""
        pages = self._extract_pages()
        lab_results = self._parse_lab_results(pages)
        latest_labs_date = self._latest_labs_date(lab_results)
        latest_labs = (
            [lab for lab in lab_results if lab.date == latest_labs_date.isoformat()]
            if latest_labs_date is not None
            else []
        )
        return LabReportExtraction(
            source=SourceReference(
                source_name=self.path.name,
                source_type="PCC Lab Results Report",
                page_start=1,
                page_end=len(pages) or None,
                extracted_at=datetime.now(tz=UTC),
            ),
            facility_id=self._parse_facility_id("\n".join(pages)),
            latest_labs=latest_labs,
            latest_labs_date=latest_labs_date.isoformat()
            if latest_labs_date is not None
            else None,
        )

    def _extract_pages(self) -> list[str]:
        """Extract text page-by-page so continuation pages keep report order."""
        if not self._is_pdf(self.path):
            return [self._document_text]
        with pdfplumber.open(self.path) as pdf:
            pages = []
            for page in pdf.pages:
                text = (page.extract_text() or "").strip()
                if text:
                    pages.append(text)
            return pages

    @classmethod
    def _parse_lab_results(cls, pages: Iterable[str]) -> list[LabResult]:
        current_date: date | None = None
        results: list[LabResult] = []
        seen: set[tuple[str | None, str, str | None]] = set()
        for page_text in pages:
            if collection_date := cls._parse_collection_date(page_text):
                current_date = collection_date
            if current_date is None:
                continue
            for line in page_text.splitlines():
                lab_result = cls._parse_result_line(line, current_date)
                if lab_result is None:
                    continue
                key = (lab_result.date, lab_result.name.casefold(), lab_result.value)
                if key in seen:
                    continue
                results.append(lab_result)
                seen.add(key)
        return results

    @staticmethod
    def _parse_result_line(line: str, collection_date: date) -> LabResult | None:
        tokens = line.strip().split()
        if len(tokens) < _MIN_RESULT_LINE_TOKENS:
            return None
        status_index = next(
            (
                index
                for index in range(len(tokens) - 1, -1, -1)
                if tokens[index] in _STATUS_TOKENS
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
        data_end = status_index - 1 if flag else status_index
        data_tokens = tokens[:data_end]
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
        value = data_tokens[value_index]
        if (
            not name
            or name in _IGNORED_LAB_NAMES
            or value in {"*", "Invalid"}
            or value.casefold() == "invalid"
        ):
            return None
        unit, reference_range = PccLabResultsExtractor._parse_unit_and_range(
            data_tokens[value_index + 1 :],
        )
        return LabResult(
            name=name,
            value=value,
            unit=unit,
            date=collection_date.isoformat(),
            reference_range=reference_range,
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
    def _parse_collection_date(text: str) -> date | None:
        match = _COLLECTION_DATE_RE.search(text)
        if match is None:
            return None
        month, day, year = (int(part) for part in match.group("date").split("/"))
        return date(year, month, day)

    @staticmethod
    def _latest_labs_date(lab_results: list[LabResult]) -> date | None:
        lab_dates = [
            datetime.fromisoformat(lab.date).date()
            for lab in lab_results
            if lab.date is not None
        ]
        return max(lab_dates) if lab_dates else None

    @staticmethod
    def _parse_facility_id(text: str) -> str | None:
        match = _FACILITY_ID_RE.search(text)
        return match.group("facility_id") if match else None
