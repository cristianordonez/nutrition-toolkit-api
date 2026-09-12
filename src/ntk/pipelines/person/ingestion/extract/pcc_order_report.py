from __future__ import annotations

import re
import typing
from datetime import UTC, date, datetime, time
from enum import StrEnum
from zoneinfo import ZoneInfo

import pymupdf

from ntk.models.sql.document import SourceAuthority

from .base import PersonExtractor
from .order_classifier import ClassifiedOrderPayload, OrderClassifier
from .registry import register_extractor

if typing.TYPE_CHECKING:
    from ntk.models.extracted_fact_create import ExtractedFactCreate

_CATEGORY_RE = re.compile(
    r"\s*(?P<category>Dietary\s*-\s*Diet|Dietary\s*-\s*Supplements|Dietary\s*-|"
    r"Enteral\s*-\s*Feed|Enteral Feed|Pharmacy|Other|Laboratory|Diagnostic)\s+"
    r"(?P<status>Active|Inactive|Discontinued|Completed)\s+"
    r"(?P<revision_date>\d{2}/\d{2}/\d{4})"
    r"(?:\s+(?P<supply_last_order_date>\d{2}/\d{2}/\d{4}))?"
    r"(?:\s+(?P<supply_reorder>[YN]))?",
)
_ORDER_PERSON_RE = re.compile(
    r"^(?P<name>[^()\n]+,\s*[^()\n]+?)\s*"
    r"\((?P<id>[A-Z]{0,4}\d+)\)\s*(?P<order>.*)$",
)
_REPORT_DATE_RE = re.compile(
    r"\bDate\s*:\s*(?P<date>"
    r"\d{1,2}/\d{1,2}/\d{4}"
    r"|[A-Z]{3,9}\s+\d{1,2},\s+\d{4}"
    r")\b",
    flags=re.IGNORECASE,
)
_REPORT_TIME_RE = re.compile(
    r"\bTime\s*:\s*(?P<time>"
    r"\d{1,2}:\d{2}(?::\d{2})?(?:\s*[AP]M)?"
    r")(?:\s*(?P<timezone>[A-Z]{2,5}))?\b",
    flags=re.IGNORECASE,
)
_REPORT_TIMEZONES = {
    "ET": "America/New_York",
    "EST": "America/New_York",
    "EDT": "America/New_York",
    "CT": "America/Chicago",
    "CST": "America/Chicago",
    "CDT": "America/Chicago",
    "MT": "America/Denver",
    "MST": "America/Denver",
    "MDT": "America/Denver",
    "PT": "America/Los_Angeles",
    "PST": "America/Los_Angeles",
    "PDT": "America/Los_Angeles",
}

ParsedPersonOrder = tuple[str | None, str | None, ClassifiedOrderPayload]
PagedPersonOrder = tuple[int, str | None, str | None, ClassifiedOrderPayload]


class OrderReportMode(StrEnum):
    """Describe whether an order report is incremental or authoritative."""

    ACTIVE_SNAPSHOT = "active_snapshot"
    INCREMENTAL = "incremental"


@register_extractor
class PccOrderReportExtractor(PersonExtractor):
    """Recognize and extract a PCC order listing report."""

    @property
    def report_mode(self) -> OrderReportMode:
        """Return authoritative semantics only for explicitly active reports."""
        if re.search(
            r"\bOrder\s+Status\s*:\s*Active\b",
            self._first_page_text,
            flags=re.IGNORECASE,
        ):
            return OrderReportMode.ACTIVE_SNAPSHOT
        return OrderReportMode.INCREMENTAL

    def is_expected_format(self) -> bool:
        """Return whether the document is a PCC order listing report."""
        return self._is_pdf(self.path) and self._first_page_contains(
            "Order Listing Report",
        )

    @property
    def source_observed_at(self) -> datetime | None:
        """Return the report's source-generated timestamp when printed."""
        date_match = _REPORT_DATE_RE.search(self._first_page_text)
        if date_match is None:
            return None
        report_date = self._parse_date(date_match.group("date"))
        if report_date is None:
            return None
        time_match = _REPORT_TIME_RE.search(self._first_page_text)
        report_time = time.min
        report_timezone = UTC
        if time_match is not None:
            parsed_time = self._parse_time(time_match.group("time"))
            if parsed_time is None:
                return None
            report_time = parsed_time
            timezone_abbreviation = time_match.group("timezone")
            if timezone_abbreviation is not None:
                timezone_name = _REPORT_TIMEZONES.get(
                    timezone_abbreviation.upper(),
                )
                if timezone_name is None:
                    if timezone_abbreviation.upper() not in {"UTC", "GMT"}:
                        return None
                else:
                    report_timezone = ZoneInfo(timezone_name)
        return datetime.combine(
            report_date,
            report_time,
            tzinfo=report_timezone,
        ).astimezone(UTC)

    async def extract(self) -> list[ExtractedFactCreate]:
        """Extract each order row as a transient fact."""
        return self._facts(allow_missing_identity=False)

    async def extract_for_demo(self) -> list[ExtractedFactCreate]:
        """Extract single-person orders without requiring source identity."""
        return self._facts(allow_missing_identity=True)

    def _facts(self, *, allow_missing_identity: bool) -> list[ExtractedFactCreate]:
        """Build order facts using strict ingestion or relaxed demo rules."""
        report_observed_at = self.source_observed_at
        if (
            self.report_mode is OrderReportMode.ACTIVE_SNAPSHOT
            and report_observed_at is None
        ):
            msg = "An active order snapshot requires a report Date timestamp"
            raise ValueError(msg)
        facility_name = self._parse_facility_name(
            self._first_page_text,
            "Order Listing Report",
        )
        return [
            self._build_extracted_fact(
                order,
                source_person_identifier=facility_resident_identifier,
                source_person_name=source_person_name,
                facility_name=facility_name,
                source_page=source_page,
                source_system="pointclickcare",
                source_record_type=order.type,
                source_authority=(
                    SourceAuthority.AUTHORITATIVE_SNAPSHOT
                    if self.report_mode is OrderReportMode.ACTIVE_SNAPSHOT
                    else SourceAuthority.STRUCTURED_RECORD
                ),
            )
            for (
                source_page,
                facility_resident_identifier,
                source_person_name,
                order,
            ) in self._extract_pdf(
                report_observed_at=report_observed_at,
                allow_missing_identity=allow_missing_identity,
            )
        ]

    def _extract_pdf(
        self,
        *,
        report_observed_at: datetime | None,
        allow_missing_identity: bool = False,
    ) -> list[PagedPersonOrder]:
        """Parse orders page by page while retaining their PDF provenance."""
        orders: list[PagedPersonOrder] = []
        seen: set[tuple[str, str, str, date | None]] = set()
        with pymupdf.open(self.path) as document:
            for page_index in range(document.page_count):
                page_text = document.load_page(page_index).get_text("text")
                page_orders = self._parse_orders(
                    page_text,
                    report_observed_at=report_observed_at,
                )
                if allow_missing_identity and not page_orders:
                    page_orders = self._parse_orders_without_identity(
                        page_text,
                        report_observed_at=report_observed_at,
                    )
                for (
                    facility_resident_identifier,
                    source_person_name,
                    order,
                ) in page_orders:
                    identity = (
                        (facility_resident_identifier or "").casefold(),
                        order.type,
                        self._normalize_summary(self._payload_text(order)),
                        order.source_revision_date,
                    )
                    if identity in seen:
                        continue
                    seen.add(identity)
                    orders.append(
                        (
                            page_index + 1,
                            facility_resident_identifier,
                            source_person_name,
                            order,
                        ),
                    )
        return orders

    @classmethod
    def _parse_orders_without_identity(
        cls,
        text: str,
        *,
        report_observed_at: datetime | None,
    ) -> list[ParsedPersonOrder]:
        """Parse a single-person demo report whose identity column was removed."""
        matches = list(_CATEGORY_RE.finditer(text))
        orders: list[ParsedPersonOrder] = []
        previous_end = 0
        for match in matches:
            summary_lines = [
                line.strip()
                for line in text[previous_end : match.start()].splitlines()
                if line.strip()
            ]
            header_end = max(
                (
                    index
                    for index, line in enumerate(summary_lines)
                    if line.casefold() == "reorder"
                ),
                default=-1,
            )
            summary = " ".join(summary_lines[header_end + 1 :]).strip()
            previous_end = match.end()
            if not summary:
                continue
            category = " ".join(match.group("category").split())
            revision_date = cls._parse_date(match.group("revision_date"))
            payloads = OrderClassifier.classify_many(
                summary,
                category=category,
                status=match.group("status"),
                observed_at=report_observed_at,
                revision_date=revision_date,
            )
            orders.extend((None, None, payload) for payload in payloads)
        return orders

    @classmethod
    def _parse_orders(
        cls,
        text: str,
        *,
        report_observed_at: datetime | None = None,
    ) -> list[ParsedPersonOrder]:
        """Parse each order with the person identifier on its row."""
        orders: list[ParsedPersonOrder] = []
        facility_resident_identifier: str | None = None
        source_person_name: str | None = None
        row_lines: list[str] = []
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line or cls._is_report_chrome(line):
                continue
            if person_match := _ORDER_PERSON_RE.match(line):
                cls._append_order(
                    orders,
                    facility_resident_identifier,
                    source_person_name,
                    row_lines,
                    report_observed_at=report_observed_at,
                )
                facility_resident_identifier = person_match.group("id").strip()
                source_person_name = person_match.group("name").strip()
                row_lines = [person_match.group("order").strip()]
            elif row_lines:
                row_lines.append(line)
        cls._append_order(
            orders,
            facility_resident_identifier,
            source_person_name,
            row_lines,
            report_observed_at=report_observed_at,
        )
        return orders

    @classmethod
    def _append_order(
        cls,
        orders: list[ParsedPersonOrder],
        facility_resident_identifier: str | None,
        source_person_name: str | None,
        row_lines: list[str],
        *,
        report_observed_at: datetime | None,
    ) -> None:
        if facility_resident_identifier is None or source_person_name is None:
            return
        parsed_orders = cls._parse_order_text(
            " ".join(row_lines),
            report_observed_at=report_observed_at,
        )
        orders.extend(
            (facility_resident_identifier, source_person_name, order)
            for order in parsed_orders
        )

    @staticmethod
    def _parse_order_text(
        order_text: str,
        *,
        report_observed_at: datetime | None = None,
    ) -> list[ClassifiedOrderPayload]:
        match = _CATEGORY_RE.search(order_text)
        if match is None:
            return []
        category = " ".join(match.group("category").split())
        summary_parts = [order_text[: match.start()].strip()]
        trailing_text = order_text[match.end() :].strip()
        if category == "Dietary -" and trailing_text.endswith("Supplements"):
            category = "Dietary - Supplements"
            trailing_text = trailing_text.removesuffix("Supplements").strip()
        if trailing_text:
            summary_parts.append(trailing_text)
        revision_date = PccOrderReportExtractor._parse_date(
            match.group("revision_date"),
        )
        summary = " ".join(part for part in summary_parts if part)
        return OrderClassifier.classify_many(
            summary,
            category=category,
            status=match.group("status"),
            observed_at=report_observed_at,
            revision_date=revision_date,
        )

    @staticmethod
    def _is_report_chrome(line: str) -> bool:
        return (
            line.startswith(
                (
                    "Order Listing Report",
                    "Facility #:",
                    "Date:",
                    "Time:",
                    "Resident:",
                    "Resident :",
                    "Resident Order",
                    "Page ",
                ),
            )
            or line == "Name Summary Category Status Date Last Order Date Reorder"
        )

    @staticmethod
    def _parse_date(value: str | None) -> date | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        for format_string in ("%m/%d/%Y", "%b %d, %Y", "%B %d, %Y"):
            try:
                return datetime.strptime(  # noqa: DTZ007
                    normalized,
                    format_string,
                ).date()
            except ValueError:
                continue
        return None

    @staticmethod
    def _parse_time(value: str) -> time | None:
        normalized = " ".join(value.upper().split())
        formats = (
            "%I:%M:%S %p",
            "%I:%M %p",
            "%H:%M:%S",
            "%H:%M",
        )
        for format_string in formats:
            try:
                return datetime.strptime(  # noqa: DTZ007
                    normalized,
                    format_string,
                ).time()
            except ValueError:
                continue
        return None

    @staticmethod
    def _normalize_summary(value: str) -> str:
        return " ".join(value.split()).casefold()

    @staticmethod
    def _payload_text(payload: ClassifiedOrderPayload) -> str:
        if getattr(payload, "instructions", None):
            return typing.cast("str", payload.instructions)
        return typing.cast("str", getattr(payload, "description", ""))
