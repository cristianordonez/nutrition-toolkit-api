"""Intermediate structural models shared by the parser and chunker."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class KnowledgeBlockType(StrEnum):
    """Distinguish retrievable guidance from document navigation and sources."""

    CONTENT = "content"
    REFERENCES = "references"
    TABLE_OF_CONTENTS = "table_of_contents"
    METADATA = "metadata"


@dataclass(frozen=True)
class KnowledgePageSpan:
    """Character range in section text originating on one physical page."""

    page_number: int
    start: int
    end: int


@dataclass(frozen=True)
class KnowledgeSection:
    """A meaningful section of knowledge content before retrieval chunking."""

    title: str | None
    breadcrumb: tuple[str, ...]
    text: str
    source_page_start: int
    source_page_end: int
    block_type: KnowledgeBlockType = KnowledgeBlockType.CONTENT
    page_spans: tuple[KnowledgePageSpan, ...] = ()

    @property
    def path(self) -> str | None:
        """Return the authoritative article hierarchy as a readable path."""
        if self.breadcrumb:
            return " > ".join(self.breadcrumb)
        return self.title
