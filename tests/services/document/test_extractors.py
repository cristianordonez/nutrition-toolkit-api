from __future__ import annotations

import typing

import pymupdf
import pytest

from ntk.services.document import DocumentExtractorService
from ntk.services.document.extractors.knowledge_extractor import DietManualExtractor

if typing.TYPE_CHECKING:
    import pathlib


def test_knowledge_extractor_reads_pdf_with_pymupdf(
    tmp_path: pathlib.Path,
) -> None:
    path = tmp_path / "manual.pdf"
    with pymupdf.open() as document:
        page = document.new_page()
        page.insert_text((72, 72), "Diet Manual clinical guidance")
        document.set_toc([[1, "Chapter 1", 1]])
        document.save(path)

    extractor = DietManualExtractor(path)

    assert extractor._document_text == "Diet Manual clinical guidance"  # noqa: SLF001


@pytest.mark.parametrize("filename", ["missing.txt", "missing.pdf"])
def test_document_extractor_service_rejects_missing_paths(
    tmp_path: pathlib.Path,
    filename: str,
) -> None:
    path = tmp_path / filename

    with pytest.raises(ValueError, match="does not exist"):
        DocumentExtractorService.find_extractor(path)
