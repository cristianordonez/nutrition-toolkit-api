from __future__ import annotations

import re
import typing
from dataclasses import dataclass

from pypdf.generic import Destination

from ntk.models.document import ChunkType, Document, DocumentChunk, DocumentType

from .base import IngestionProcessor

if typing.TYPE_CHECKING:
    from collections.abc import Sequence

MAX_CHUNK_TOKENS = 750
_TOKEN_PATTERN = re.compile(r"\w+|[^\w\s]", re.UNICODE)
_PARAGRAPH_PATTERN = re.compile(r"\n\s*\n+")
_SENTENCE_PATTERN = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")


@dataclass(frozen=True)
class _TextUnit:
    text: str
    page_number: int


@dataclass(frozen=True)
class _PageText:
    text: str
    page_number: int


@dataclass(frozen=True)
class _OutlineEntry:
    title: str
    level: int
    page_number: int


class KnowledgeProcessor(IngestionProcessor):
    """Process educational material into bounded, section-aware chunks."""

    def create_chunks(self, document: Document) -> list[DocumentChunk]:
        """Split knowledge by outline section and bounded text units."""
        chunks: list[DocumentChunk] = []
        for pages, titles in self._sections():
            metadata = {
                "chapter": titles[0] if titles else None,
                "section": titles[1] if len(titles) > 1 else None,
                "heading": titles[-1] if titles else None,
            }
            for units in self._pack_pages(pages):
                chunks.extend(
                    self._create_chunk(
                        document,
                        len(chunks),
                        "\n\n".join(unit.text for unit in units),
                        {
                            **metadata,
                            "page_start": units[0].page_number,
                            "page_end": units[-1].page_number,
                        },
                    ),
                )
        return chunks

    def _sections(self) -> list[tuple[list[_PageText], list[str]]]:
        """Group every page under the deepest active outline hierarchy."""
        pages = [
            _PageText(text=text, page_number=index)
            for index, text in enumerate(self.page_texts, start=1)
        ]
        if not pages:
            return []

        hierarchy: list[str] = []
        titles_by_page: dict[int, list[str]] = {}
        for entry in sorted(
            self._outline_entries(),
            key=lambda item: (item.page_number, item.level),
        ):
            hierarchy = hierarchy[: entry.level]
            hierarchy.append(entry.title)
            titles_by_page[entry.page_number] = hierarchy.copy()

        sections: list[tuple[list[_PageText], list[str]]] = []
        active_titles: list[str] = []
        active_pages: list[_PageText] = []
        for page in pages:
            page_titles = titles_by_page.get(page.page_number, active_titles)
            if active_pages and page_titles != active_titles:
                sections.append((active_pages, active_titles))
                active_pages = []
            active_titles = page_titles
            active_pages.append(page)
        if active_pages:
            sections.append((active_pages, active_titles))
        return sections

    def _pack_pages(self, pages: list[_PageText]) -> list[list[_TextUnit]]:
        """Pack paragraphs without crossing the configured token target."""
        chunks: list[list[_TextUnit]] = []
        current: list[_TextUnit] = []
        for page in pages:
            for unit in self._page_units(page):
                candidate = "\n\n".join(item.text for item in [*current, unit])
                if current and self._token_count(candidate) > MAX_CHUNK_TOKENS:
                    chunks.append(current)
                    current = []
                current.append(unit)
        if current:
            chunks.append(current)
        return chunks

    def _page_units(self, page: _PageText) -> list[_TextUnit]:
        """Split a page at paragraphs, then sentences, then safe word boundaries."""
        units: list[_TextUnit] = []
        for raw_paragraph in _PARAGRAPH_PATTERN.split(page.text.strip()):
            paragraph = " ".join(raw_paragraph.split())
            if paragraph:
                units.extend(self._split_oversized(paragraph, page.page_number))
        return units

    def _outline_entries(self) -> list[_OutlineEntry]:
        """Interpret the raw PDF outline for manual section chunking."""
        if self.path.suffix.lower() != ".pdf":
            return []
        entries: list[_OutlineEntry] = []

        def visit(items: Sequence[object], level: int) -> None:
            for item in items:
                if isinstance(item, list):
                    visit(item, level + 1)
                elif isinstance(item, Destination):
                    try:
                        page_index = self.pdf_reader.destination_page_number(item)
                    except (KeyError, ValueError):
                        continue
                    if page_index is not None:
                        entries.append(
                            _OutlineEntry(
                                title=str(item.title).strip(),
                                level=level,
                                page_number=page_index + 1,
                            ),
                        )

        visit(self.pdf_reader.outline, 0)
        return entries

    def _split_oversized(self, text: str, page_number: int) -> list[_TextUnit]:
        if self._token_count(text) <= MAX_CHUNK_TOKENS:
            return [_TextUnit(text, page_number)]
        pieces: list[str] = []
        current = ""
        for sentence in _SENTENCE_PATTERN.split(text):
            candidate = f"{current} {sentence}".strip()
            if current and self._token_count(candidate) > MAX_CHUNK_TOKENS:
                pieces.extend(self._split_words(current))
                current = sentence
            else:
                current = candidate
        if current:
            pieces.extend(self._split_words(current))
        return [_TextUnit(piece, page_number) for piece in pieces if piece]

    def _split_words(self, text: str) -> list[str]:
        """Split text that remains oversized, including unbroken strings."""
        if self._token_count(text) <= MAX_CHUNK_TOKENS:
            return [text]
        pieces: list[str] = []
        current: list[str] = []
        for word in text.split():
            candidate = " ".join([*current, word])
            if current and self._token_count(candidate) > MAX_CHUNK_TOKENS:
                pieces.append(" ".join(current))
                current = []
            if self._token_count(word) > MAX_CHUNK_TOKENS:
                if current:
                    pieces.append(" ".join(current))
                    current = []
                pieces.extend(self._split_characters(word))
            else:
                current.append(word)
        if current:
            pieces.append(" ".join(current))
        return pieces

    @staticmethod
    def _split_characters(text: str) -> list[str]:
        """Bound pathological strings that contain no usable split point."""
        character_limit = MAX_CHUNK_TOKENS * 4
        return [
            text[index : index + character_limit]
            for index in range(0, len(text), character_limit)
        ]

    @staticmethod
    def _token_count(text: str) -> int:
        """Conservatively estimate model tokens without a tokenizer dependency."""
        lexical_tokens = len(_TOKEN_PATTERN.findall(text))
        character_tokens = (len(text) + 3) // 4
        return max(lexical_tokens, character_tokens)


class DietManualProcessor(KnowledgeProcessor):
    """Process diet-manual reference content."""

    document_type = DocumentType.DIET_MANUAL
    chunk_type = ChunkType.DIET_MANUAL
    format_markers = ("diet manual",)


class NutritionCareManualProcessor(KnowledgeProcessor):
    """Process nutrition-care-manual reference content."""

    document_type = DocumentType.NUTRITION_CARE_MANUAL
    chunk_type = ChunkType.NUTRITION_CARE_MANUAL
    format_markers = ("nutrition care manual",)
