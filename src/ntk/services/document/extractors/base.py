from __future__ import annotations

import abc
import functools
import typing

import pymupdf

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
    def _is_pdf(file: pathlib.Path) -> bool:
        return file.suffix.lower() == ".pdf"
