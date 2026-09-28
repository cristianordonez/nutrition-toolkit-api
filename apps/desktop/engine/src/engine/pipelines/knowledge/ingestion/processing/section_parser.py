"""Keep article bodies together; navigation labels are context, not content.

PDF bookmarks, not title casing of body lines, define hierarchy. Tables, lists,
wrapped headings, and sibling subheadings must never grow a breadcrumb chain.
For callers without outline metadata, printed breadcrumbs provide a fallback.
"""

from __future__ import annotations

import re
import typing

from .structure import KnowledgeBlockType, KnowledgePageSpan, KnowledgeSection

if typing.TYPE_CHECKING:
    from collections.abc import Sequence

    from engine.models.knowledge import ExtractedKnowledgePage

_REFERENCE_HEADING = re.compile(
    r"^(?:(?:selected\s+)?references?(?:\s*:.*)?|bibliography|"
    r"practice[- ]related (?:guidelines|resources))$",
    re.IGNORECASE,
)
_METADATA_HEADING = re.compile(
    r"^(?:welcome(?:\s+to.*)?|reviewers?|contributors?|acknowledg(?:e)?ments?|"
    r"publication information|about this manual|copyright)$",
    re.IGNORECASE,
)
_TOC_HEADING = re.compile(
    r"^(?:table of )?contents$|^(?:subject )?index$",
    re.IGNORECASE,
)
_FOOTER = re.compile(
    r"^(?:copyright\s+\d{4}|©\s*\d{4}|content release date\s*:|"
    r"page\s+\d+(?:\s+of\s+\d+)?\s*$)",
    re.IGNORECASE,
)
_TOC_ENTRY = re.compile(r"^\.{3,}\S|^.+\.{2,}\s*\d+\s*$")
_MIN_TOC_ENTRIES = 2
_FALLBACK_HEADINGS = frozenset(
    {
        "nutritionassessment",
        "nutritiondiagnosis",
        "nutritionintervention",
        "nutritionmonitoringandevaluation",
        "foodnutritionrelatedhistory",
        "anthropometricmeasurements",
        "clienthistory",
        "comparativestandards",
    },
)


def _heading_key(text: str) -> str:
    return re.sub(r"[\W_]+", "", text).casefold()


class KnowledgeStructureParser:
    """Parse substantive, cross-page articles with precise page offsets."""

    def parse(self, pages: Sequence[ExtractedKnowledgePage]) -> list[KnowledgeSection]:
        """Exclude front matter/references and retain each article's body."""
        sections: list[KnowledgeSection] = []
        path: tuple[str, ...] = ()
        segments: list[tuple[int, str]] = []
        state = KnowledgeBlockType.CONTENT

        def flush() -> None:
            if segments:
                texts: list[str] = []
                spans: list[KnowledgePageSpan] = []
                offset = 0
                for page_number, text in segments:
                    texts.append(text)
                    spans.append(
                        KnowledgePageSpan(page_number, offset, offset + len(text)),
                    )
                    offset += len(text) + 2  # paragraph separator between pages
                sections.append(
                    KnowledgeSection(
                        title=path[-1] if path else None,
                        breadcrumb=path,
                        text="\n\n".join(texts),
                        source_page_start=spans[0].page_number,
                        source_page_end=spans[-1].page_number,
                        page_spans=tuple(spans),
                    ),
                )
                segments.clear()

        for page in pages:
            page_path, lines = self._page_content(page)
            if page_path and page_path != path:
                flush()
                path = page_path
                state = self._classify(path[-1])
            if not page.section_path and self._is_toc(lines):
                flush()
                state = KnowledgeBlockType.TABLE_OF_CONTENTS
                continue

            body: list[str] = []
            for line in lines:
                classification = self._classify(line)
                # The outline/page check handles navigation. An 'Index'
                # column inside a clinical table is ordinary body text.
                if classification in {
                    KnowledgeBlockType.REFERENCES,
                    KnowledgeBlockType.METADATA,
                }:
                    self._append_body(segments, page.page_number, body, path)
                    body = []
                    flush()
                    state = classification
                elif state is KnowledgeBlockType.CONTENT:
                    body.append(line)
            self._append_body(segments, page.page_number, body, path)
        flush()
        return sections

    @staticmethod
    def _append_body(
        segments: list[tuple[int, str]],
        page_number: int,
        lines: list[str],
        path: tuple[str, ...],
    ) -> None:
        text = "\n".join(lines).strip()
        # A divider or an illustration's repeated article title is not guidance.
        labels = {_heading_key(part) for part in path} | _FALLBACK_HEADINGS
        if text and any(_heading_key(line) not in labels for line in lines if line):
            segments.append((page_number, text))

    def _page_content(
        self,
        page: ExtractedKnowledgePage,
    ) -> tuple[tuple[str, ...], list[str]]:
        lines = [" ".join(line.split()) for line in page.text.splitlines()]
        lines = [line for line in lines if not _FOOTER.match(line)]
        while lines and not lines[0]:
            lines.pop(0)
        path = page.section_path
        if lines and self._is_navigation(lines[0]):
            header_length = self._header_length(lines)
            navigation = " ".join(lines[:header_length])
            if not path:
                path = tuple(
                    part.strip() for part in navigation.split(">") if part.strip()
                )
            lines = lines[header_length:]
        while lines and not lines[0]:
            lines.pop(0)

        return self._strip_article_title(
            path,
            lines,
            has_outline=bool(page.section_path),
        )

    @staticmethod
    def _strip_article_title(
        path: tuple[str, ...],
        lines: list[str],
        *,
        has_outline: bool,
    ) -> tuple[tuple[str, ...], list[str]]:
        # The visible article title may wrap or repair a malformed printed
        # breadcrumb (e.g. 'Practice > Related Guidelines'). Outline paths win.
        if path and lines:
            for count in range(1, min(4, len(lines)) + 1):
                title = " ".join(lines[:count]).strip()
                key = _heading_key(title)
                if key == _heading_key(path[-1]):
                    lines = lines[count:]
                    break
                if not has_outline and count == 1:
                    matched = next(
                        (
                            size
                            for size in range(1, len(path) + 1)
                            if _heading_key(" ".join(path[-size:])) == key
                        ),
                        None,
                    )
                    if matched:
                        path = (*path[:-matched], title)
                        lines = lines[1:]
                        break
                    if key in _FALLBACK_HEADINGS:
                        path = (*path, title)
                        lines = lines[1:]
                        break
        return path, lines

    @staticmethod
    def _is_navigation(line: str) -> bool:
        parts = [part.strip() for part in line.split(">") if part.strip()]
        # Do not mistake clinical comparisons such as 'Glucose > 200' for paths.
        return (
            ">" in line
            and bool(parts)
            and all(part.strip() and part.strip()[0].isalpha() for part in parts)
        )

    @staticmethod
    def _header_length(lines: list[str]) -> int:
        # Compatibility with plain page text: locate the repeated visible title
        # immediately following a wrapped breadcrumb.
        paragraph_end = lines.index("") if "" in lines else len(lines)
        for count in range(1, min(5, len(lines), paragraph_end)):
            parts = [
                part.strip()
                for part in " ".join(lines[:count]).split(">")
                if part.strip()
            ]
            if any(
                _heading_key(" ".join(parts[-size:])) == _heading_key(lines[count])
                for size in range(1, len(parts) + 1)
            ):
                return count
        if len(lines) > 1 and _heading_key(lines[1]) in _FALLBACK_HEADINGS:
            return 1
        # Extraction preserves the breadcrumb's PDF block, including wrapping.
        if paragraph_end < len(lines):
            return paragraph_end
        return 1

    @staticmethod
    def _classify(heading: str) -> KnowledgeBlockType:
        heading = heading.strip().rstrip(":").strip()
        if _REFERENCE_HEADING.fullmatch(heading):
            return KnowledgeBlockType.REFERENCES
        if _METADATA_HEADING.fullmatch(heading):
            return KnowledgeBlockType.METADATA
        if _TOC_HEADING.fullmatch(heading):
            return KnowledgeBlockType.TABLE_OF_CONTENTS
        return KnowledgeBlockType.CONTENT

    @staticmethod
    def _is_toc(lines: list[str]) -> bool:
        return (
            any(_TOC_HEADING.fullmatch(line) for line in lines[:2])
            or sum(bool(_TOC_ENTRY.match(line)) for line in lines) >= _MIN_TOC_ENTRIES
        )


__all__ = ["KnowledgeStructureParser"]
