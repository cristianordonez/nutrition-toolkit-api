"""Knowledge-ingestion specialization of the shared extractor contract."""

from __future__ import annotations

import typing
from hashlib import sha256
from html import unescape

import pymupdf

from engine.models.knowledge import ExtractedKnowledgePage
from engine.models.sql.knowledge import Knowledge
from engine.pipelines.extraction import DocumentExtractor

if typing.TYPE_CHECKING:
    from engine.models.sql.knowledge import KnowledgeType


class KnowledgeExtractor(DocumentExtractor[list[ExtractedKnowledgePage]]):
    """Base class for reusable clinical knowledge document extractors."""

    knowledge_type: typing.ClassVar[KnowledgeType]

    async def extract(self) -> list[ExtractedKnowledgePage]:
        """Retain article boundaries and paragraph breaks from the source PDF."""
        if not self.is_expected_format():
            msg = f"Attempted to read unsupported file format: {self.path}"
            raise TypeError(msg)
        pages: list[ExtractedKnowledgePage] = []
        with pymupdf.open(self.path) as document:
            paths = _outline_paths(document.get_toc(), len(document))
            for page_number, page in enumerate(document, start=1):
                # Preserve PDF text-block order: sorting individual lines would
                # interleave wrapped cells of tables in these manuals.
                text = "\n\n".join(
                    block[4].strip()
                    for block in page.get_text("blocks")
                    if block[6] == 0 and block[4].strip()
                )
                if text:
                    pages.append(
                        ExtractedKnowledgePage(
                            page_number=page_number,
                            text=text,
                            section_path=paths.get(page_number, ()),
                        ),
                    )
        return pages

    def create_knowledge(self) -> Knowledge:
        """Create the persisted identity for this knowledge source."""
        return Knowledge(
            filename=self.path.name,
            knowledge_type=self.knowledge_type,
            file_hash=sha256(self.path.read_bytes()).hexdigest(),
        )


def _outline_paths(
    outline: list[list[typing.Any]],
    page_count: int,
) -> dict[int, tuple[str, ...]]:
    """Expand bookmarks to pages, including NCM's dot-indented flat outlines.

    NCM uses synthetic 'Title' bookmarks and puts most real entries at PDF
    level 2. Its groups of three leading dots carry the actual hierarchy.
    Other PDFs can use normal bookmark levels.
    """
    dotted = any(str(row[1]).startswith("...") for row in outline)
    boundaries: dict[int, tuple[str, ...]] = {}
    path: tuple[str, ...] = ()
    for level, raw_title, page_number in outline:
        title = " ".join(unescape(str(raw_title)).split())
        if dotted and title == "Title":
            continue
        if not 1 <= page_number <= page_count:
            continue
        depth = (
            (len(title) - len(title.lstrip("."))) // 3 if dotted else max(0, level - 1)
        )
        title = title.lstrip(".").strip()
        if title:
            path = (*path[:depth], title)
            boundaries[page_number] = path
    paths: dict[int, tuple[str, ...]] = {}
    path = ()
    for page_number in range(1, page_count + 1):
        path = boundaries.get(page_number, path)
        if path:
            paths[page_number] = path
    return paths


__all__ = ["KnowledgeExtractor"]
