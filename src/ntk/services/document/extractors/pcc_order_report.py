from __future__ import annotations

import re
from datetime import UTC, datetime

from ntk.models.resident_data import OrderReportExtraction, PccOrder, SourceReference
from ntk.models.sql.resident import MedicationData, SupplementData, TubeFeedingData

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
_RESIDENT_RE = re.compile(
    r"^Resident\s*:\s*(?P<name>.+?)\s*\((?P<id>[A-Z]{0,4}\d+)\)",
)
_FREQUENCY_PATTERNS = (
    (re.compile(r"\b(one time a day|once daily|qd|daily)\b", re.IGNORECASE), "QD"),
    (re.compile(r"\b(two times a day|bid|twice daily)\b", re.IGNORECASE), "BID"),
    (re.compile(r"\b(three times a day|tid)\b", re.IGNORECASE), "TID"),
    (re.compile(r"\b(four times a day|qid)\b", re.IGNORECASE), "QID"),
    (
        re.compile(
            r"\b(every \d+ hours|every \d+ hour|q\d+h|q \d+ h)\b",
            re.IGNORECASE,
        ),
        None,
    ),
    (re.compile(r"\b(at bedtime|bedtime|hs)\b", re.IGNORECASE), "HS"),
    (re.compile(r"\b(as needed|prn)\b", re.IGNORECASE), "PRN"),
)
_AMOUNT_RE = re.compile(
    r"\b(?P<amount>\d+(?:\.\d+)?\s*(?:ounces?|oz|ml|mL|grams?|gm|tabs?|tablets?))\b",
    re.IGNORECASE,
)
_TEXTURE_RE = re.compile(
    r"\bdiet\s+(?P<texture>[A-Za-z ]+?)\s+texture\b",
    re.IGNORECASE,
)
_CONSISTENCY_RE = re.compile(
    r"\b(?P<consistency>[A-Za-z ]+?)\s+consistency\b",
    re.IGNORECASE,
)
_RATE_RE = re.compile(
    r"\b(?P<rate>\d+(?:\.\d+)?\s*(?:mL|ml|cc|units?)\s*/?\s*(?:hr|hour|day)?)\b",
    re.IGNORECASE,
)
_FLUSH_RE = re.compile(
    r"\b(?P<flush>(?:flush|fwf|water flush)[^.]+)",
    re.IGNORECASE,
)


@register_extractor
class PccOrderReportExtractor(BaseExtractor):
    """Recognize and extract a PCC order listing report."""

    def is_expected_format(self) -> bool:
        """Return whether the document is a PCC order listing report."""
        return self._first_page_contains("Order Listing Report")

    def extract(self) -> OrderReportExtraction:
        """Extract nutrition-relevant facts from an order listing report."""
        document_text = self._document_text
        resident_name, facility_id = self._parse_resident(document_text)
        orders = self._parse_orders(document_text, resident_name, facility_id)
        active_orders = [
            order
            for order in orders
            if (order.order_status or "").casefold() == "active"
        ]
        return OrderReportExtraction(
            source=SourceReference(
                source_name=self.path.name,
                source_type="PCC Order Listing Report",
                page_start=1,
                page_end=None,
                extracted_at=datetime.now(tz=UTC),
            ),
            facility_id=facility_id,
            orders=orders,
            medications=self._extract_medications(active_orders),
            diet=self._extract_diet(active_orders),
            diet_texture=self._extract_diet_texture(active_orders),
            liquid_consistency=self._extract_liquid_consistency(active_orders),
            supplements=self._extract_supplements(active_orders),
            tubefeed_order=self._extract_tubefeed(active_orders),
        )

    @staticmethod
    def _parse_resident(text: str) -> tuple[str | None, str | None]:
        for line in text.splitlines():
            match = _RESIDENT_RE.match(line.strip())
            if match:
                return match.group("name").strip(), match.group("id").strip()
        return None, None

    @classmethod
    def _parse_orders(
        cls,
        text: str,
        resident_name: str | None,
        facility_id: str | None,
    ) -> list[PccOrder]:
        if resident_name is None or facility_id is None:
            return []
        marker = f"{resident_name} ({facility_id})"
        blocks: list[list[str]] = []
        current: list[str] = []
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line or cls._is_report_chrome(line):
                continue
            if line.startswith(marker):
                if current:
                    blocks.append(current)
                current = [line.removeprefix(marker).strip()]
            elif current:
                current.append(line)
        if current:
            blocks.append(current)
        return [
            order
            for block in blocks
            if (order := cls._parse_order_block(block, resident_name)) is not None
        ]

    @staticmethod
    def _parse_order_block(block: list[str], resident_name: str) -> PccOrder | None:
        text = " ".join(block)
        match = _CATEGORY_RE.search(text)
        if match is None:
            return None
        category = " ".join(match.group("category").split())
        summary = text[: match.start()].strip()
        trailing = text[match.end() :].strip()
        if category == "Dietary -" and trailing.endswith("Supplements"):
            category = "Dietary - Supplements"
            trailing = trailing.removesuffix("Supplements").strip()
        if trailing:
            summary = f"{summary} {trailing}".strip()
        return PccOrder(
            resident_name=resident_name,
            order_summary=summary,
            order_category=category,
            order_status=match.group("status"),
            revision_date=match.group("revision_date"),
            supply_last_order_date=match.group("supply_last_order_date"),
            supply_reorder=match.group("supply_reorder"),
        )

    @staticmethod
    def _is_report_chrome(line: str) -> bool:
        return (
            line.startswith(
                ("Facility #:", "Date:", "Time:", "Resident Order", "Page "),
            )
            or line == "Name Summary Category Status Date Last Order Date Reorder"
        )

    @staticmethod
    def _extract_medications(orders: list[PccOrder]) -> list[MedicationData]:
        medications = []
        for order in orders:
            summary = order.order_summary
            summary_lower = summary.casefold()
            if order.order_category != "Pharmacy":
                continue
            if not (
                "by mouth" in summary_lower
                or "oral" in summary_lower
                or "insulin" in summary_lower
            ):
                continue
            medications.append(
                MedicationData(
                    name=PccOrderReportExtractor._extract_medication_name(summary),
                    dose=PccOrderReportExtractor._extract_amount(summary),
                    route=PccOrderReportExtractor._extract_route(summary),
                    frequency=PccOrderReportExtractor._extract_frequency(summary),
                    indication=PccOrderReportExtractor._extract_indication(summary),
                ),
            )
        return medications

    @staticmethod
    def _extract_diet(orders: list[PccOrder]) -> str | None:
        diet_order = PccOrderReportExtractor._first_order(orders, "Dietary - Diet")
        if diet_order is None:
            return None
        summary = diet_order.order_summary
        diet_match = re.search(
            r"^(?P<diet>.+?\bdiet\b)",
            summary,
            flags=re.IGNORECASE,
        )
        return diet_match.group("diet").strip() if diet_match else summary

    @staticmethod
    def _extract_diet_texture(orders: list[PccOrder]) -> str | None:
        diet_order = PccOrderReportExtractor._first_order(orders, "Dietary - Diet")
        if diet_order is None:
            return None
        match = _TEXTURE_RE.search(diet_order.order_summary)
        return match.group("texture").strip() if match else None

    @staticmethod
    def _extract_liquid_consistency(orders: list[PccOrder]) -> str | None:
        diet_order = PccOrderReportExtractor._first_order(orders, "Dietary - Diet")
        if diet_order is None:
            return None
        match = _CONSISTENCY_RE.search(diet_order.order_summary)
        return match.group("consistency").strip() if match else None

    @staticmethod
    def _extract_supplements(orders: list[PccOrder]) -> list[SupplementData]:
        supplements = []
        for order in orders:
            if order.order_category != "Dietary - Supplements":
                continue
            supplements.append(
                SupplementData(
                    name=PccOrderReportExtractor._extract_supplement_name(
                        order.order_summary,
                    ),
                    amount=PccOrderReportExtractor._extract_amount(order.order_summary),
                    frequency=PccOrderReportExtractor._extract_frequency(
                        order.order_summary,
                    ),
                ),
            )
        return supplements

    @staticmethod
    def _extract_tubefeed(orders: list[PccOrder]) -> TubeFeedingData | None:
        enteral_order = PccOrderReportExtractor._first_order(orders, "Enteral Feed")
        if enteral_order is None:
            return None
        summary = enteral_order.order_summary
        flush_match = _FLUSH_RE.search(summary)
        return TubeFeedingData(
            formula=PccOrderReportExtractor._extract_tubefeed_formula(summary),
            rate=(
                rate_match.group("rate").strip()
                if (rate_match := _RATE_RE.search(summary))
                else None
            ),
            schedule=PccOrderReportExtractor._extract_frequency(summary),
            flushes=flush_match.group("flush").strip() if flush_match else None,
        )

    @staticmethod
    def _first_order(orders: list[PccOrder], category: str) -> PccOrder | None:
        return next(
            (order for order in orders if order.order_category == category),
            None,
        )

    @staticmethod
    def _extract_medication_name(summary: str) -> str:
        before_instruction = re.split(
            r"\b(?:Give|Inject|Apply|Insert|Administer|Take)\b",
            summary,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0]
        return (
            before_instruction.strip() or summary.split(" for ", maxsplit=1)[0].strip()
        )

    @staticmethod
    def _extract_route(summary: str) -> str | None:
        summary_lower = summary.casefold()
        if "by mouth" in summary_lower or " oral " in f" {summary_lower} ":
            return "by mouth"
        if "insulin" in summary_lower:
            return "insulin"
        return None

    @staticmethod
    def _extract_indication(summary: str) -> str | None:
        parts = re.split(r"\bfor\b", summary, maxsplit=1, flags=re.IGNORECASE)
        return parts[1].strip() if len(parts) > 1 else None

    @staticmethod
    def _extract_amount(summary: str) -> str | None:
        match = _AMOUNT_RE.search(summary)
        return match.group("amount").strip() if match else None

    @staticmethod
    def _extract_frequency(summary: str) -> str | None:
        for pattern, normalized in _FREQUENCY_PATTERNS:
            match = pattern.search(summary)
            if match:
                return normalized or match.group(1)
        return None

    @staticmethod
    def _extract_supplement_name(summary: str) -> str:
        name = re.split(
            r"\b(?:PO|by mouth|one time|two times|three times|four times|"
            r"bid|qd|tid|qid)\b",
            summary,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0]
        return name.strip() or summary

    @staticmethod
    def _extract_tubefeed_formula(summary: str) -> str | None:
        formula = re.split(
            r"\b(?:at|@|rate|flush|fwf|water flush|one time|two times|continuous)\b",
            summary,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0]
        return formula.strip() or None
