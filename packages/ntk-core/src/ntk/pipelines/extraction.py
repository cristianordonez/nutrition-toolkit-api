"""Shared document-extractor contract and file-reading helpers."""

from __future__ import annotations

import abc
import functools
import typing

import pymupdf

if typing.TYPE_CHECKING:
    import pathlib

ResultT = typing.TypeVar("ResultT")


class DocumentExtractor(abc.ABC, typing.Generic[ResultT]):
    """Shared contract for recognizing and extracting a document."""

    def __init__(self, path: pathlib.Path) -> None:
        """Store the source document path."""
        self.path = path

    @abc.abstractmethod
    def is_expected_format(self) -> bool:
        """Return whether the source matches this extractor's format."""
        pass  # noqa: PIE790

    @abc.abstractmethod
    async def extract(self) -> ResultT:
        """Extract the domain-specific result from the source document."""
        pass  # noqa: PIE790

    @functools.cached_property
    def _document_pages(self) -> tuple[tuple[int, str], ...]:
        """Extract and cache one-based page text without retaining an open file."""
        if not self.is_expected_format():
            msg = f"Attempted to read unsupported file format: {self.path}"
            raise TypeError(msg)
        with pymupdf.open(self.path) as document:
            return tuple(
                (page_number + 1, document.load_page(page_number).get_text().strip())
                for page_number in range(document.page_count)
            )

    @functools.cached_property
    def _document_text(self) -> str:
        """Extract and cache readable content without retaining an open file."""
        return "\n".join(
            page_text for _, page_text in self._document_pages if page_text
        )

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
        """Return whether a path has a PDF extension."""
        return file.suffix.lower() == ".pdf"


__all__ = ["DocumentExtractor"]
