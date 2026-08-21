from __future__ import annotations

import typing

from pypdf import PdfReader as PyPdfReader

if typing.TYPE_CHECKING:
    import pathlib
    from collections.abc import Sequence

    from pypdf._page import PageObject
    from pypdf.generic import Destination


class PdfReader:
    """Provide direct access to a PDF without interpreting its contents."""

    def __init__(self, path: pathlib.Path) -> None:
        """Initialize the reader.

        :param path: Full path to file.
        :raises ValueError: file does not exist
        :raises ValueError: file does not have .pdf extension
        """
        if not path.is_file():
            msg = f"PDF file does not exist: {path}"
            raise ValueError(msg)
        if path.suffix.lower() != ".pdf":
            msg = f"Path is not a PDF file: {path}"
            raise ValueError(msg)
        self._reader = PyPdfReader(path)

    @property
    def pages(self) -> Sequence[PageObject]:
        """Return the underlying PDF pages."""
        return self._reader.pages

    @property
    def outline(self) -> list[typing.Any]:
        """Return the underlying PDF outline."""
        return self._reader.outline

    def destination_page_number(self, destination: Destination) -> int | None:
        """Delegate destination lookup to pypdf."""
        return self._reader.get_destination_page_number(destination)
