from __future__ import annotations

import re
import typing
from datetime import UTC, date, datetime, time

import pymupdf
from pydantic import BaseModel, Field

from ntk.models.extracted_fact_create import ExtractedFactCreate, LabPayload

from .base import BaseExtractor
from .registry import register_extractor

_COLLECTION_DATE_RE = re.compile(
    r"\bCollection Date\s*:\s*(?P<date>\d{1,2}/\d{1,2}/\d{4})\b"
    r"(?:\s+(?P<hour>\d{1,2}):(?P<minute>\d{2})"
    r"(?:\s*(?P<period>AM|PM))?)?",
    flags=re.IGNORECASE,
)
_ADMISSION_DATE_RE = re.compile(
    r"\b(?:Admit|Admission) Date\s*:\s*(?P<date>\d{1,2}/\d{1,2}/\d{4})\b",
    flags=re.IGNORECASE,
)
_DOB_RE = re.compile(
    r"\bDOB\s*:?\s*(?P<date>\d{1,2}/\d{1,2}/\d{4})\b",
    flags=re.IGNORECASE,
)
_PERSON_NAME_PART = r"[A-Za-z][A-Za-z'.\-]*(?:\s+[A-Za-z][A-Za-z'.\-]*)*"
_RESIDENT_RE = re.compile(
    r"\bResident\s*:\s*(?P<name>[^\n(]+?)\s*"
    r"(?:\(\s*NAME\s+ALERT\s*\)\s*)?"
    r"\((?P<id>[A-Z]{0,4}\d+)\)",
    flags=re.IGNORECASE,
)
_BODY_RESIDENT_RE = re.compile(
    rf"^\s*(?P<name>{_PERSON_NAME_PART},\s*{_PERSON_NAME_PART})\s*"
    r"(?:\(\s*NAME\s+ALERT\s*\)\s*)?"
    r"\((?P<id>[A-Z]{0,4}\d+)\)",
    flags=re.IGNORECASE | re.MULTILINE,
)
_ORDER_NUMBER_RE = re.compile(
    r"\bOrder[ \t]*#[ \t]*:[ \t]*(?P<value>[^\n]*)",
    flags=re.IGNORECASE,
)
_SOURCE_KEY_RE = re.compile(
    r"\bSource[ \t]*Key[ \t]*:?[ \t]*(?P<value>[^\n]*)",
    flags=re.IGNORECASE,
)
_LABORATORY_RE = re.compile(r"\bLaboratory\s*:", flags=re.IGNORECASE)
_PAGE_NUMBER_RE = re.compile(
    r"\bPage\s+(?P<current>\d+)\s+of\s+(?P<total>\d+)\b",
    flags=re.IGNORECASE,
)
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
ResidentLab = tuple[int, str, str | None, date | None, LabPayload]
ResidentLabKey = tuple[str, datetime | None, str, float | str]


class _LabReportMetadata(typing.TypedDict):
    resident_identifier: str | None
    resident_name: str | None
    collection_date: datetime | None
    order_number: str | None
    source_key: str | None
    date_of_birth: date | None


class LabReportPage(BaseModel):
    """One physical PDF page belonging to a logical lab report."""

    page_number: int
    text: str
    words: list[Word] = Field(exclude=True)


class LabReportDocument(BaseModel):
    """A logical lab report assembled from one or more PDF pages."""

    resident_identifier: str
    resident_name: str
    collection_date: datetime | None
    order_number: str | None
    source_key: str | None
    date_of_birth: date | None
    start_page: int
    end_page: int
    text: str
    pages: list[LabReportPage] = Field(exclude=True)


class LabReportSplitter:
    """Split sequential PDF pages into logical resident lab reports."""

    @classmethod
    def split(cls, document: pymupdf.Document) -> list[LabReportDocument]:
        """Return logical reports while retaining each physical source page."""
        reports: list[LabReportDocument] = []
        current_pages: list[LabReportPage] = []
        metadata: _LabReportMetadata | None = None
        previous_report_page: int | None = None

        for page_index in range(document.page_count):
            page = document.load_page(page_index)
            text = page.get_text("text").strip()
            page_metadata = cls._metadata(text)
            report_page, _ = cls._page_number(text)
            starts_report = cls._is_full_header(text)
            continues_report = cls._continues_report(
                metadata,
                page_metadata,
                previous_report_page,
                report_page,
            )

            if current_pages and (
                (starts_report and not continues_report)
                or (report_page == 1 and not continues_report)
            ):
                reports.append(cls._build_report(metadata, current_pages))
                current_pages = []
                metadata = None

            if metadata is None:
                if page_metadata["resident_identifier"] is None:
                    continue
                metadata = page_metadata
            else:
                metadata = cls._merge_metadata(metadata, page_metadata)

            current_pages.append(
                LabReportPage(
                    page_number=page_index + 1,
                    text=text,
                    words=page.get_text("words", sort=True),
                ),
            )
            previous_report_page = report_page

        if current_pages:
            reports.append(cls._build_report(metadata, current_pages))
        return reports

    @staticmethod
    def _metadata(text: str) -> _LabReportMetadata:
        resident = PccLabResultsExtractor._parse_resident(text)  # noqa: SLF001
        if resident is None:
            match = _BODY_RESIDENT_RE.search(text)
            resident = (
                (match.group("id").strip(), match.group("name").strip())
                if match is not None
                else None
            )
        return {
            "resident_identifier": resident[0] if resident else None,
            "resident_name": resident[1] if resident else None,
            "collection_date": PccLabResultsExtractor._parse_collection_datetime(  # noqa: SLF001
                text,
            ),
            "order_number": LabReportSplitter._parse_identifier(
                text,
                _ORDER_NUMBER_RE,
                zero_is_empty=True,
            ),
            "source_key": LabReportSplitter._parse_identifier(
                text,
                _SOURCE_KEY_RE,
            ),
            "date_of_birth": PccLabResultsExtractor._parse_date(  # noqa: SLF001
                text,
                _DOB_RE,
            ),
        }

    @staticmethod
    def _parse_identifier(
        text: str,
        pattern: re.Pattern[str],
        *,
        zero_is_empty: bool = False,
    ) -> str | None:
        match = pattern.search(text)
        if match is None:
            return None
        value = match.group("value").strip()
        if not value or (zero_is_empty and value == "0"):
            return None
        return value

    @staticmethod
    def _page_number(text: str) -> tuple[int | None, int | None]:
        match = _PAGE_NUMBER_RE.search(text)
        if match is None:
            return None, None
        return int(match.group("current")), int(match.group("total"))

    @staticmethod
    def _is_full_header(text: str) -> bool:
        return bool(
            PccLabResultsExtractor._parse_resident(text)  # noqa: SLF001
            and _COLLECTION_DATE_RE.search(text)
            and _ORDER_NUMBER_RE.search(text)
            and _SOURCE_KEY_RE.search(text)
            and _LABORATORY_RE.search(text),
        )

    @staticmethod
    def _continues_report(
        current: _LabReportMetadata | None,
        incoming: _LabReportMetadata,
        previous_page: int | None,
        incoming_page: int | None,
    ) -> bool:
        if current is None or incoming_page is None or incoming_page <= 1:
            return False
        if previous_page is not None and incoming_page != previous_page + 1:
            return False
        old_resident = current["resident_identifier"]
        new_resident = incoming["resident_identifier"]
        if (
            old_resident is not None
            and new_resident is not None
            and old_resident.casefold() != new_resident.casefold()
        ):
            return False

        old_source_key = current["source_key"]
        new_source_key = incoming["source_key"]
        if old_source_key is not None and new_source_key is not None:
            return old_source_key.casefold() == new_source_key.casefold()

        for field_name in ("order_number", "collection_date"):
            old_value = current[field_name]
            new_value = incoming[field_name]
            if old_value is not None and new_value is not None:
                return old_value == new_value
        return True

    @staticmethod
    def _merge_metadata(
        current: _LabReportMetadata,
        incoming: _LabReportMetadata,
    ) -> _LabReportMetadata:
        return _LabReportMetadata(
            resident_identifier=current["resident_identifier"]
            or incoming["resident_identifier"],
            resident_name=current["resident_name"] or incoming["resident_name"],
            collection_date=current["collection_date"] or incoming["collection_date"],
            order_number=current["order_number"] or incoming["order_number"],
            source_key=current["source_key"] or incoming["source_key"],
            date_of_birth=current["date_of_birth"] or incoming["date_of_birth"],
        )

    @staticmethod
    def _build_report(
        metadata: _LabReportMetadata | None,
        pages: list[LabReportPage],
    ) -> LabReportDocument:
        if metadata is None:
            msg = "Cannot build a lab report without resident metadata"
            raise ValueError(msg)
        return LabReportDocument(
            resident_identifier=str(metadata["resident_identifier"]),
            resident_name=str(metadata["resident_name"]),
            collection_date=metadata["collection_date"],
            order_number=metadata["order_number"],
            source_key=metadata["source_key"],
            date_of_birth=metadata["date_of_birth"],
            start_page=pages[0].page_number,
            end_page=pages[-1].page_number,
            text="\n".join(page.text for page in pages),
            pages=pages,
        )


@register_extractor
class PccLabResultsExtractor(BaseExtractor):
    """Recognize and extract a PCC lab results report."""

    def is_expected_format(self) -> bool:
        """Return whether the document is a PCC lab results report."""
        return self._is_pdf(self.path) and self._first_page_contains(
            "Lab Results",
            "Laboratory Results",
        )

    async def extract(self) -> list[ExtractedFactCreate]:
        """Extract each laboratory result as a transient fact."""
        facility_name = self._parse_facility_name(
            self._first_page_text,
            "Lab Results Report",
            "Laboratory Results",
        )
        return [
            self._build_extracted_fact(
                lab_result,
                facility_resident_identifier=facility_resident_identifier,
                resident_name=resident_name,
                facility_name=facility_name,
                date_of_birth=date_of_birth,
                source_page=source_page,
            )
            for (
                source_page,
                facility_resident_identifier,
                resident_name,
                date_of_birth,
                lab_result,
            ) in self._extract_pdf()
        ]

    def _extract_pdf(self) -> list[ResidentLab]:
        results: list[ResidentLab] = []
        with pymupdf.open(self.path) as document:
            reports = LabReportSplitter.split(document)
            for report in reports:
                if report.collection_date is None:
                    continue
                for report_page in report.pages:
                    page_results = self._parse_words(
                        report_page.words,
                        report.collection_date,
                    )
                    results.extend(
                        (
                            report_page.page_number,
                            report.resident_identifier,
                            report.resident_name,
                            report.date_of_birth,
                            result,
                        )
                        for result in page_results
                    )
        return self._deduplicate(results)

    @classmethod
    def _parse_page_words(
        cls,
        page: pymupdf.Page,
        collection_at: date | datetime,
    ) -> list[LabPayload]:
        return cls._parse_words(page.get_text("words", sort=True), collection_at)

    @classmethod
    def _parse_words(
        cls,
        words: list[Word],
        collection_at: date | datetime,
    ) -> list[LabPayload]:
        """Parse lab rows from one physical page's positioned words."""
        lines = cls._group_words(words)
        header_index, boundaries = cls._find_result_columns(lines)
        if header_index is None:
            return []
        results = []
        for line_words in lines[header_index + 1 :]:
            values = cls._assign_to_columns(line_words, boundaries)
            result = cls._lab_result_from_columns(values, collection_at)
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
        collection_at: date | datetime,
    ) -> LabPayload | None:
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
        return LabPayload(
            name=name,
            result=result,
            unit=values["unit"] or None,
            reference_range=values["reference_range"] or None,
            flag=values["flag"] or None,
            observed_at=PccLabResultsExtractor._result_datetime(collection_at),
        )

    @staticmethod
    def _parse_result_line(
        line: str,
        collection_at: date | datetime,
    ) -> LabPayload | None:
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
        return LabPayload(
            name=name,
            result=result,
            unit=unit,
            reference_range=reference_range,
            observed_at=PccLabResultsExtractor._result_datetime(collection_at),
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
    def _deduplicate(results: list[ResidentLab]) -> list[ResidentLab]:
        unique: list[ResidentLab] = []
        seen: set[ResidentLabKey] = set()
        for (
            source_page,
            facility_resident_identifier,
            resident_name,
            date_of_birth,
            result,
        ) in results:
            key = (
                facility_resident_identifier,
                result.observed_at,
                result.name.casefold(),
                result.result,
            )
            if key not in seen:
                seen.add(key)
                unique.append(
                    (
                        source_page,
                        facility_resident_identifier,
                        resident_name,
                        date_of_birth,
                        result,
                    ),
                )
        return unique

    @staticmethod
    def _parse_collection_date(text: str) -> date | None:
        return PccLabResultsExtractor._parse_date(text, _COLLECTION_DATE_RE)

    @staticmethod
    def _parse_collection_datetime(text: str) -> datetime | None:
        match = _COLLECTION_DATE_RE.search(text)
        if match is None:
            return None
        month, day, year = (int(part) for part in match.group("date").split("/"))
        hour = int(match.group("hour") or 0)
        minute = int(match.group("minute") or 0)
        period = match.group("period")
        if period is not None:
            hour %= 12
            if period.casefold() == "pm":
                hour += 12
        return datetime(year, month, day, hour, minute, tzinfo=UTC)

    @staticmethod
    def _parse_date(text: str, pattern: re.Pattern[str]) -> date | None:
        match = pattern.search(text)
        if match is None:
            return None
        month, day, year = (int(part) for part in match.group("date").split("/"))
        return date(year, month, day)

    @staticmethod
    def _result_datetime(collection_at: date | datetime) -> datetime:
        if isinstance(collection_at, datetime):
            return collection_at
        return datetime.combine(collection_at, time.min, tzinfo=UTC)

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
    def _parse_facility_resident_identifier(text: str) -> str | None:
        resident = PccLabResultsExtractor._parse_resident(text)
        return resident[0] if resident else None

    @staticmethod
    def _parse_resident(text: str) -> tuple[str, str] | None:
        match = _RESIDENT_RE.search(text)
        if match is None:
            return None
        return match.group("id").strip(), match.group("name").strip()
