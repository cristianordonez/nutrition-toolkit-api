"""Knowledge-document processing facade."""

from __future__ import annotations

import typing

from .chunker import KnowledgeChunker
from .section_parser import KnowledgeStructureParser

if typing.TYPE_CHECKING:
    from engine.models.knowledge import ExtractedKnowledgePage, KnowledgeChunkCreate


class KnowledgeContentProcessor:
    """Convert extracted knowledge pages into retrieval-ready chunks.

    Responsibilities are delegated intentionally:

    Extractor
        -> extracts physical document content

    KnowledgeStructureParser
        -> removes document noise
        -> identifies structural hierarchy
        -> excludes references / TOC / metadata
        -> joins content across pages

    KnowledgeChunker
        -> creates embedding/retrieval-sized windows
        -> injects structural context
    """

    def __init__(
        self,
        *,
        parser: KnowledgeStructureParser | None = None,
        chunker: KnowledgeChunker | None = None,
    ) -> None:
        """Use the article parser and model-aware chunker unless injected."""
        self._parser = parser or KnowledgeStructureParser()
        self._chunker = chunker or KnowledgeChunker()

    def build_chunks(
        self,
        pages: typing.Sequence[ExtractedKnowledgePage],
    ) -> list[KnowledgeChunkCreate]:
        """Build body-bearing chunks from the extracted article pages."""
        sections = self._parser.parse(pages)

        return self._chunker.chunk(sections)


__all__ = ["KnowledgeContentProcessor"]
