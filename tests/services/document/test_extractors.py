from __future__ import annotations

import typing

import pytest
from pypdf import PdfWriter

from ntk.services.document import DocumentExtractorService
from ntk.services.document.extractors.knowledge_extractor import DietManualExtractor

if typing.TYPE_CHECKING:
    import pathlib

    from pypdf.generic import Destination


def test_knowledge_extractor_exposes_cached_pdf_reader(
    tmp_path: pathlib.Path,
) -> None:
    path = tmp_path / "manual.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.add_outline_item("Chapter 1", 0)
    with path.open("wb") as stream:
        writer.write(stream)

    extractor = DietManualExtractor(path)
    reader = extractor.reader

    assert len(reader.pages) == 1
    assert len(reader.outline) == 1
    destination = typing.cast("Destination", reader.outline[0])
    assert reader.get_destination_page_number(destination) == 0
    assert extractor.reader is reader


@pytest.mark.parametrize("filename", ["missing.txt", "missing.pdf"])
def test_document_extractor_service_rejects_missing_paths(
    tmp_path: pathlib.Path,
    filename: str,
) -> None:
    path = tmp_path / filename

    with pytest.raises(ValueError, match="does not exist"):
        DocumentExtractorService.find_extractor(path)
