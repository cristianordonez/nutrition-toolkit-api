from __future__ import annotations

import typing

import pytest
from pypdf import PdfWriter

from ntk.services.document import PdfReader

if typing.TYPE_CHECKING:
    import pathlib


def test_pdf_reader_exposes_raw_pages_and_outline(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "manual.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.add_outline_item("Chapter 1", 0)
    with path.open("wb") as stream:
        writer.write(stream)

    reader = PdfReader(path)

    assert len(reader.pages) == 1
    assert len(reader.outline) == 1
    assert reader.destination_page_number(reader.outline[0]) == 0


@pytest.mark.parametrize("filename", ["document.txt", "missing.pdf"])
def test_pdf_reader_rejects_invalid_paths(
    tmp_path: pathlib.Path,
    filename: str,
) -> None:
    path = tmp_path / filename
    if path.suffix != ".pdf":
        path.touch()

    with pytest.raises(ValueError, match=r"PDF file|not a PDF"):
        PdfReader(path)
