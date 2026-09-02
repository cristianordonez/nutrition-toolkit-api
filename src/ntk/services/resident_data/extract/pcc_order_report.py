from __future__ import annotations

import re
from datetime import date
from enum import StrEnum

import pymupdf

from ntk.models.extracted_fact_create import ExtractedFactCreate, OrderPayload

from .base import BaseExtractor
from .registry import register_extractor

_CATEGORY_RE = re.compile(
    r"\s*(?P<category>Dietary\s*-\s*Diet|Dietary\s*-\s*Supplements|Dietary\s*-|"
    r"Enteral Feed|Pharmacy|Other|Laboratory|Diagnostic)\s+"
    r"(?P<status>Active|Inactive|Discontinued|Completed)\s+"
    r"(?P<revision_date>\d{2}/\d{2}/\d{4})"
    r"(?:\s+(?P<supply_last_order_date>\d{2}/\d{2}/\d{4}))?"
    r"(?:\s+(?P<supply_reorder>[YN]))?",
)
_ORDER_RESIDENT_RE = re.compile(
    r"^(?P<name>[^()\n]+,\s*[^()\n]+?)\s*"
    r"\((?P<id>[A-Z]{0,4}\d+)\)\s*(?P<order>.*)$",
)

ResidentOrder = tuple[str, str, OrderPayload]
PagedResidentOrder = tuple[int, str, str, OrderPayload]


class OrderReportMode(StrEnum):
    """Describe whether an order report is incremental or authoritative."""

    ACTIVE_SNAPSHOT = "active_snapshot"
    INCREMENTAL = "incremental"


@register_extractor
class PccOrderReportExtractor(BaseExtractor):
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

    async def extract(self) -> list[ExtractedFactCreate]:
        """Extract each order row as a transient fact."""
        facility_name = self._parse_facility_name(
            self._first_page_text,
            "Order Listing Report",
        )
        return [
            self._build_extracted_fact(
                order,
                facility_resident_identifier=facility_resident_identifier,
                resident_name=resident_name,
                facility_name=facility_name,
                source_page=source_page,
            )
            for source_page, facility_resident_identifier, resident_name, order in (
                self._extract_pdf()
            )
        ]

    def _extract_pdf(self) -> list[PagedResidentOrder]:
        """Parse orders page by page while retaining their PDF provenance."""
        orders: list[PagedResidentOrder] = []
        seen: set[tuple[str, str, date | None]] = set()
        with pymupdf.open(self.path) as document:
            for page_index in range(document.page_count):
                page_orders = self._parse_orders(
                    document.load_page(page_index).get_text("text"),
                )
                for (
                    facility_resident_identifier,
                    resident_name,
                    order,
                ) in page_orders:
                    identity = (
                        facility_resident_identifier.casefold(),
                        self._normalize_summary(order.summary),
                        order.revision_date,
                    )
                    if identity in seen:
                        continue
                    seen.add(identity)
                    orders.append(
                        (
                            page_index + 1,
                            facility_resident_identifier,
                            resident_name,
                            order,
                        ),
                    )
        return orders

    @classmethod
    def _parse_orders(
        cls,
        text: str,
    ) -> list[ResidentOrder]:
        """Parse each order with the resident identifier on its row."""
        orders: list[ResidentOrder] = []
        facility_resident_identifier: str | None = None
        resident_name: str | None = None
        row_lines: list[str] = []
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line or cls._is_report_chrome(line):
                continue
            if resident_match := _ORDER_RESIDENT_RE.match(line):
                cls._append_order(
                    orders,
                    facility_resident_identifier,
                    resident_name,
                    row_lines,
                )
                facility_resident_identifier = resident_match.group("id").strip()
                resident_name = resident_match.group("name").strip()
                row_lines = [resident_match.group("order").strip()]
            elif row_lines:
                row_lines.append(line)
        cls._append_order(
            orders,
            facility_resident_identifier,
            resident_name,
            row_lines,
        )
        return orders

    @classmethod
    def _append_order(
        cls,
        orders: list[ResidentOrder],
        facility_resident_identifier: str | None,
        resident_name: str | None,
        row_lines: list[str],
    ) -> None:
        if facility_resident_identifier is None or resident_name is None:
            return
        if order := cls._parse_order_text(" ".join(row_lines)):
            orders.append((facility_resident_identifier, resident_name, order))

    @staticmethod
    def _parse_order_text(order_text: str) -> OrderPayload | None:
        match = _CATEGORY_RE.search(order_text)
        if match is None:
            return None
        category = " ".join(match.group("category").split())
        summary_parts = [order_text[: match.start()].strip()]
        trailing_text = order_text[match.end() :].strip()
        if category == "Dietary -" and trailing_text.endswith("Supplements"):
            category = "Dietary - Supplements"
            trailing_text = trailing_text.removesuffix("Supplements").strip()
        if trailing_text:
            summary_parts.append(trailing_text)
        return OrderPayload(
            summary=" ".join(part for part in summary_parts if part),
            category=category,
            status=match.group("status"),
            revision_date=PccOrderReportExtractor._parse_date(
                match.group("revision_date"),
            ),
            supply_last_order_date=PccOrderReportExtractor._parse_date(
                match.group("supply_last_order_date"),
            ),
            supply_reorder=match.group("supply_reorder"),
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
        month, day, year = (int(part) for part in value.split("/"))
        return date(year, month, day)

    @staticmethod
    def _normalize_summary(value: str) -> str:
        return " ".join(value.split()).casefold()
