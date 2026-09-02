from __future__ import annotations

import abc
import functools
import typing
from datetime import date  # noqa: TC003

import pymupdf

from ntk.models.extracted_fact_create import ExtractedFactCreate, FactPayload

if typing.TYPE_CHECKING:
    import pathlib


class BaseExtractor(abc.ABC):
    """Base contract for recognizing one document format."""

    def __init__(self, path: pathlib.Path) -> None:
        """Store the source document path."""
        self.path = path

    @abc.abstractmethod
    def is_expected_format(self) -> bool:
        """Return whether the source matches this extractor's format."""
        pass  # noqa: PIE790

    @abc.abstractmethod
    async def extract(self) -> list[ExtractedFactCreate]:
        """Extract contents of file."""
        pass  # noqa: PIE790

    def _build_extracted_fact(  # noqa: PLR0913
        self,
        payload: FactPayload,
        *,
        facility_resident_identifier: str | None = None,
        resident_name: str | None = None,
        facility_name: str | None = None,
        date_of_birth: date | None = None,
        sex: str | None = None,
        height_in: float | None = None,
        source_page: int | None = None,
    ) -> ExtractedFactCreate:
        """Build one deterministic fact attributed to this extractor."""
        return ExtractedFactCreate(
            facility_resident_identifier=facility_resident_identifier,
            resident_name=resident_name,
            facility_name=facility_name,
            date_of_birth=date_of_birth,
            sex=sex,
            height_in=height_in,
            source_page=source_page,
            payload=payload,
            confidence=1.0,
            confidence_reason="Deterministic report extraction",
        )

    @functools.cached_property
    def _document_text(self) -> str:
        """Extract and cache readable content without retaining an open file."""
        if not self.is_expected_format():
            msg = f"Attempted to read unsupported file format: {self.path}"
            raise TypeError(msg)
        with pymupdf.open(self.path) as document:
            pages = [
                document.load_page(page_number).get_text().strip()
                for page_number in range(document.page_count)
            ]
        return "\n".join(page_text for page_text in pages if page_text)

    @functools.cached_property
    def _first_page_text(self) -> str:
        """Extract and cache first-page text without retaining an open PDF."""
        with pymupdf.open(self.path) as document:
            if document.page_count == 0:
                return ""
            return document.load_page(0).get_text().strip()

    def _first_page_contains(self, *markers: str) -> bool:
        """Return whether first-page text contains any marker."""
        page_text = self._first_page_text.casefold()
        return any(marker.casefold() in page_text for marker in markers)

    @staticmethod
    def _parse_facility_name(text: str, *report_titles: str) -> str | None:
        """Return the facility name printed immediately below a PCC report title."""
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        titles = {title.casefold() for title in report_titles}
        for index, line in enumerate(lines):
            if line.casefold() not in titles:
                continue
            adjacent_lines = []
            if index + 1 < len(lines):
                adjacent_lines.append(lines[index + 1])
            if index > 0:
                adjacent_lines.append(lines[index - 1])
            for candidate in adjacent_lines:
                if not candidate.startswith(
                    (
                        "Facility",
                        "Time:",
                        "Date:",
                        "Resident:",
                        "User:",
                        "Laboratory:",
                        "Reviewed By",
                        "Latest Version",
                    ),
                ):
                    return candidate
        return None

    @staticmethod
    def _is_pdf(file: pathlib.Path) -> bool:
        return file.suffix.lower() == ".pdf"
