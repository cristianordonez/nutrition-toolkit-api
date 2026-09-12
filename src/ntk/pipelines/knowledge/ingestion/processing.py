"""Deterministic cleanup and page-aware chunking for knowledge manuals."""

from __future__ import annotations

import re
import typing
from collections import Counter
from dataclasses import dataclass

from ntk.models.knowledge import (
    ExtractedKnowledgePage,
    KnowledgeChunkCreate,
    KnowledgeSectionType,
)
from ntk.utils.tokens import sliding_window

_REFERENCE_HEADING_RE = re.compile(
    r"^(?:selected\s+)?references(?:\s*:\s*[\w /&-]+)?$|^bibliography$",
    flags=re.IGNORECASE,
)
_TOC_HEADING_RE = re.compile(
    r"^(?:table\s+of\s+)?contents$|^(?:subject\s+)?index$",
    flags=re.IGNORECASE,
)
_METADATA_HEADING_RE = re.compile(
    r"^(?:reviewers?|contributors?|acknowledg(?:e)?ments?|publication information|"
    r"about this manual|copyright)$",
    flags=re.IGNORECASE,
)
_DOCUMENT_TITLE_RE = re.compile(
    r"^(?:nutrition care manual|diet manual)$",
    flags=re.IGNORECASE,
)
_TOC_ENTRY_RE = re.compile(r"^.{3,}?\s*\.{2,}\s*\d+\s*$")
_PAGE_NUMBER_RE = re.compile(r"^(?:page\s+)?\d+(?:\s+of\s+\d+)?$", re.IGNORECASE)
_SUBSECTION_HEADING_RE = re.compile(
    r"^(?:definition|purpose|indications?|contraindications?|description|"
    r"nutritional adequacy|recommendations?|implementation|foods? (?:allowed|"
    r"recommended|not allowed|to avoid)|monitoring)(?:\s*:)?$",
    flags=re.IGNORECASE,
)
_CLINICAL_TITLE_TOPIC_RE = re.compile(
    r"\b(?:diet|nutrition|feeding|malnutrition|dysphagia|liquid|iddsi|hydration|"
    r"weight|diabetes|diabetic|renal|cardiac|guidance|guidelines|therapy|care)\b",
    flags=re.IGNORECASE,
)
_INLINE_METADATA_RES = (
    re.compile(r"(?:copyright|©|all rights reserved)", re.IGNORECASE),
    re.compile(r"^(?:reviewed|prepared|contributed)\s+by\b", re.IGNORECASE),
    re.compile(
        r"^(?:publication|release|revision|revised|published|last updated)\s+date\b",
        re.IGNORECASE,
    ),
)
_MIN_TOC_ENTRIES = 2
_MIN_REPEATED_PAGE_LINES = 2
_MAX_TITLE_CHARACTERS = 90
_MAX_TITLE_WORDS = 12


@dataclass(frozen=True)
class _ContentSegment:
    page_number: int
    section_title: str | None
    text: str


class KnowledgeContentProcessor:
    """Exclude document noise and chunk only substantive page content."""

    def build_chunks(
        self,
        pages: typing.Sequence[ExtractedKnowledgePage],
    ) -> list[KnowledgeChunkCreate]:
        """Return semantic chunks whose source page remains deterministic."""
        chunks: list[KnowledgeChunkCreate] = []
        for segment in self._content_segments(pages):
            chunks.extend(self._chunk_segment(segment))
        return chunks

    @staticmethod
    def classify_heading(line: str) -> KnowledgeSectionType | None:
        """Classify an exact structural heading without matching inline prose."""
        normalized = line.strip().rstrip(":").strip()
        if _REFERENCE_HEADING_RE.fullmatch(normalized):
            return KnowledgeSectionType.REFERENCES
        if _TOC_HEADING_RE.fullmatch(normalized):
            return KnowledgeSectionType.TABLE_OF_CONTENTS
        if _METADATA_HEADING_RE.fullmatch(normalized):
            return KnowledgeSectionType.METADATA
        return None

    def _content_segments(
        self,
        pages: typing.Sequence[ExtractedKnowledgePage],
    ) -> list[_ContentSegment]:
        repeated_noise = self._repeated_page_noise(pages)
        state = KnowledgeSectionType.CONTENT
        section_title: str | None = None
        segments: list[_ContentSegment] = []
        for page in pages:
            page_segments, state, section_title = self._page_segments(
                page,
                state,
                section_title,
                repeated_noise,
            )
            segments.extend(page_segments)
        return segments

    def _page_segments(
        self,
        page: ExtractedKnowledgePage,
        state: KnowledgeSectionType,
        section_title: str | None,
        repeated_noise: set[str],
    ) -> tuple[list[_ContentSegment], KnowledgeSectionType, str | None]:
        lines = [line.strip() for line in page.text.splitlines() if line.strip()]
        if self._has_toc_entries(lines):
            state = KnowledgeSectionType.TABLE_OF_CONTENTS
        segments: list[_ContentSegment] = []
        content_lines: list[str] = []
        segment_title = section_title
        for index, line in enumerate(lines):
            if self._is_noise(line, repeated_noise):
                continue
            classification = self.classify_heading(line)
            if classification is not None:
                self._append_segment(
                    segments,
                    page.page_number,
                    segment_title,
                    content_lines,
                )
                content_lines = []
                state = classification
                continue
            next_line = lines[index + 1] if index + 1 < len(lines) else None
            if state is not KnowledgeSectionType.CONTENT:
                if not self._looks_like_section_title(line, next_line, strict=True):
                    continue
                state = KnowledgeSectionType.CONTENT
                section_title = line
                segment_title = line
                content_lines.append(line)
                continue
            if not content_lines and self._looks_like_section_title(
                line,
                next_line,
                strict=section_title is not None,
            ):
                section_title = line
                segment_title = line
            content_lines.append(line)
        self._append_segment(
            segments,
            page.page_number,
            segment_title,
            content_lines,
        )
        return segments, state, section_title

    @staticmethod
    def _append_segment(
        segments: list[_ContentSegment],
        page_number: int,
        section_title: str | None,
        lines: list[str],
    ) -> None:
        if lines:
            segments.append(
                _ContentSegment(
                    page_number=page_number,
                    section_title=section_title,
                    text="\n".join(lines),
                ),
            )

    @staticmethod
    def _chunk_segment(segment: _ContentSegment) -> list[KnowledgeChunkCreate]:
        chunks: list[KnowledgeChunkCreate] = []
        for text in sliding_window(segment.text):
            content = text.strip()
            if not content:
                continue
            title = segment.section_title
            if title and not content.casefold().startswith(title.casefold()):
                content = f"{title}\n\n{content}"
            chunks.append(
                KnowledgeChunkCreate(
                    content=content,
                    section_title=title,
                    source_page_start=segment.page_number,
                    source_page_end=segment.page_number,
                ),
            )
        return chunks

    @staticmethod
    def _has_toc_entries(lines: typing.Sequence[str]) -> bool:
        return (
            sum(bool(_TOC_ENTRY_RE.fullmatch(line)) for line in lines)
            >= _MIN_TOC_ENTRIES
        )

    @classmethod
    def _repeated_page_noise(
        cls,
        pages: typing.Sequence[ExtractedKnowledgePage],
    ) -> set[str]:
        candidates: Counter[str] = Counter()
        for page in pages:
            lines = [line.strip() for line in page.text.splitlines() if line.strip()]
            boundary_lines = {*lines[:2], *lines[-2:]}
            candidates.update(
                cls._normalize_line(line)
                for line in boundary_lines
                if cls._is_repeated_noise_candidate(line)
            )
        return {
            line
            for line, count in candidates.items()
            if count >= _MIN_REPEATED_PAGE_LINES
        }

    @staticmethod
    def _is_noise(line: str, repeated_noise: set[str]) -> bool:
        return KnowledgeContentProcessor._normalize_line(
            line,
        ) in repeated_noise or KnowledgeContentProcessor._is_inline_metadata(line)

    @staticmethod
    def _is_repeated_noise_candidate(line: str) -> bool:
        normalized = line.casefold()
        return (
            "manual" in normalized
            or "academy of nutrition and dietetics" in normalized
            or "all rights reserved" in normalized
            or bool(_PAGE_NUMBER_RE.fullmatch(line.strip()))
        )

    @staticmethod
    def _is_inline_metadata(line: str) -> bool:
        stripped = line.strip()
        return (
            bool(_PAGE_NUMBER_RE.fullmatch(stripped))
            or bool(_DOCUMENT_TITLE_RE.fullmatch(stripped))
            or any(pattern.search(stripped) for pattern in _INLINE_METADATA_RES)
        )

    @staticmethod
    def _looks_like_section_title(
        line: str,
        next_line: str | None,
        *,
        strict: bool,
    ) -> bool:
        stripped = line.strip().rstrip(":").strip()
        words = stripped.split()
        if (
            not stripped
            or len(stripped) > _MAX_TITLE_CHARACTERS
            or not 1 < len(words) <= _MAX_TITLE_WORDS
            or stripped.endswith((".", ";", ","))
            or _SUBSECTION_HEADING_RE.fullmatch(stripped)
            or _TOC_ENTRY_RE.fullmatch(stripped)
        ):
            return False
        heading_case = stripped.isupper() or all(
            word[:1].isupper() or word.casefold() in {"and", "for", "of", "the", "to"}
            for word in words
        )
        if not heading_case:
            return False
        followed_by_subsection = bool(
            next_line and _SUBSECTION_HEADING_RE.fullmatch(next_line.strip()),
        )
        if strict:
            return followed_by_subsection or bool(
                _CLINICAL_TITLE_TOPIC_RE.search(stripped),
            )
        return True

    @staticmethod
    def _normalize_line(line: str) -> str:
        return " ".join(line.casefold().split())


__all__ = ["KnowledgeContentProcessor"]
