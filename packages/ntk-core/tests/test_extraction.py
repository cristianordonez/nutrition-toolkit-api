"""Tests for the shared, generic extraction contract."""

from __future__ import annotations

import asyncio
import inspect
import typing

import pymupdf
import pytest

from ntk.pipelines.extraction import DocumentExtractor

if typing.TYPE_CHECKING:
    import pathlib


class TextExtractor(DocumentExtractor[str]):
    """Concrete shared extractor used to exercise document mechanics."""

    def is_expected_format(self) -> bool:
        return self._is_pdf(self.path)

    async def extract(self) -> str:
        return self._document_text


def _write_pdf(path: pathlib.Path, *pages: str) -> None:
    with pymupdf.open() as document:
        for text in pages:
            page = document.new_page()
            page.insert_text((20, 40), text)
        document.save(path)


def test_document_extractor_is_generic_abstract_contract() -> None:
    assert inspect.isabstract(DocumentExtractor)


def test_shared_document_helpers_and_generic_extract(
    tmp_path: pathlib.Path,
) -> None:
    source = tmp_path / "manual.PDF"
    _write_pdf(source, "Diet Manual", "Nutrition guidance")
    extractor = TextExtractor(source)

    assert DocumentExtractor._is_pdf(source)  # noqa: SLF001
    assert extractor._first_page_contains("diet manual")  # noqa: SLF001
    assert extractor._first_page_text == "Diet Manual"  # noqa: SLF001
    assert asyncio.run(extractor.extract()) == "Diet Manual\nNutrition guidance"


def test_shared_document_text_rejects_unrecognized_format(
    tmp_path: pathlib.Path,
) -> None:
    source = tmp_path / "manual.txt"
    source.write_text("Diet Manual")

    with pytest.raises(TypeError, match="unsupported file format"):
        asyncio.run(TextExtractor(source).extract())
