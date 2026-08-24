from __future__ import annotations

import abc
import functools
import typing

import pdfplumber

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

    def extract(self) -> object:
        """Extract available file content for downstream structured processing."""
        return self._document_text

    @functools.cached_property
    def _document_text(self) -> str:
        """Extract and cache readable content without retaining an open file."""
        if not self._is_pdf(self.path):
            return self.path.read_text(encoding="utf-8", errors="replace")
        with pdfplumber.open(self.path) as pdf:
            return "\n".join(
                text
                for page in pdf.pages
                if (text := (page.extract_text() or "").strip())
            )

    @functools.cached_property
    def _first_page_text(self) -> str:
        """Extract and cache first-page text without retaining an open PDF."""
        if not self._is_pdf(self.path):
            return ""
        with pdfplumber.open(self.path) as pdf:
            if not pdf.pages:
                return ""
            return (pdf.pages[0].extract_text() or "").strip()

    def _first_page_contains(self, *markers: str) -> bool:
        """Return whether first-page text contains any marker."""
        page_text = self._first_page_text.casefold()
        return any(marker.casefold() in page_text for marker in markers)

    @staticmethod
    def _is_pdf(file: pathlib.Path) -> bool:
        return file.suffix.lower() == ".pdf"
