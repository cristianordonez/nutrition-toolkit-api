"""Paragraph-aware windows that fit the bundled embedding model, context included."""

from __future__ import annotations

import functools
import json
import re
import typing
from bisect import bisect_left, bisect_right

from tokenizers import Tokenizer

from engine.models.knowledge import KnowledgeChunkCreate
from engine.paths import bundled_embedding_model_dir

from .structure import KnowledgeBlockType

if typing.TYPE_CHECKING:
    from collections.abc import Sequence

    from .structure import KnowledgeSection


@functools.lru_cache(maxsize=1)
def _embedding_tokenizer() -> tuple[Tokenizer, int]:
    """Read only the bundled tokenizer/config, not a second embedding model."""
    directory = bundled_embedding_model_dir()
    tokenizer = Tokenizer.from_file(str(directory / "tokenizer.json"))
    tokenizer.no_padding()
    tokenizer.no_truncation()
    config = json.loads((directory / "sentence_bert_config.json").read_text())
    return tokenizer, int(config["max_seq_length"])


class KnowledgeChunker:
    """Window article bodies without truncating what gets embedded."""

    def __init__(self, *, overlap_tokens: int = 32) -> None:
        """Configure the maximum overlap; actual overlap is bounded per window."""
        if overlap_tokens < 0:
            msg = "Overlap cannot be negative"
            raise ValueError(msg)
        self.overlap_tokens = overlap_tokens

    def chunk(self, sections: Sequence[KnowledgeSection]) -> list[KnowledgeChunkCreate]:
        """Create substantive chunks with context and per-window page provenance."""
        chunks: list[KnowledgeChunkCreate] = []
        for section in sections:
            if section.block_type is not KnowledgeBlockType.CONTENT:
                continue
            text = section.text.strip()
            if not text or text.casefold() in {
                (section.title or "").casefold(),
                (section.path or "").casefold(),
            }:
                continue
            chunks.extend(self._chunk_section(section))
        return chunks

    def _chunk_section(self, section: KnowledgeSection) -> list[KnowledgeChunkCreate]:
        tokenizer, limit = _embedding_tokenizer()
        prefix = self._context(section.path or "", tokenizer, limit)
        budget = limit - len(tokenizer.encode(prefix).ids)
        offsets = tokenizer.encode(section.text, add_special_tokens=False).offsets
        ends = [end for _, end in offsets]
        # Prefer whole paragraphs, then sentences, once at least half the token
        # budget is filled. Oversized paragraphs still use bounded windows.
        paragraph_ends = [m.start() for m in re.finditer(r"\n\s*\n", section.text)]
        sentence_ends = [m.start() for m in re.finditer(r"(?<=[.!?])\s+", section.text)]
        natural_starts = sorted(
            {
                bisect_right(ends, position)
                for position in (*paragraph_ends, *sentence_ends)
            },
        )
        chunks: list[KnowledgeChunkCreate] = []
        start = 0
        while start < len(offsets):
            end = min(start + budget, len(offsets))
            if end < len(offsets):
                for boundaries in (paragraph_ends, sentence_ends):
                    stop = bisect_right(boundaries, offsets[end - 1][1])
                    if stop:
                        candidate = bisect_right(ends, boundaries[stop - 1])
                        if candidate >= start + max(1, budget // 2):
                            end = candidate
                            break
            char_start = offsets[start][0]
            char_end = offsets[end - 1][1]
            content = prefix + section.text[char_start:char_end].strip()
            # Re-tokenization at a WordPiece boundary can change token counts.
            while len(tokenizer.encode(content).ids) > limit and end > start + 1:
                end -= 1
                char_end = offsets[end - 1][1]
                content = prefix + section.text[char_start:char_end].strip()
            pages = [
                span.page_number
                for span in section.page_spans
                if span.start < char_end and span.end > char_start
            ]
            chunks.append(
                KnowledgeChunkCreate(
                    content=content,
                    section_title=section.title,
                    section_path=section.path,
                    source_page_start=min(pages)
                    if pages
                    else section.source_page_start,
                    source_page_end=max(pages) if pages else section.source_page_end,
                ),
            )
            if end == len(offsets):
                break  # Never emit an extra chunk containing only overlap.
            overlap = min(self.overlap_tokens, (end - start) // 4)
            start = end - overlap
            boundary = bisect_left(natural_starts, start)
            if boundary < len(natural_starts) and natural_starts[boundary] <= end:
                start = natural_starts[boundary]
            # Start at a word boundary rather than the middle of a WordPiece.
            while (
                start < end
                and offsets[start][0] > 0
                and not section.text[offsets[start][0] - 1].isspace()
            ):
                start += 1
        return chunks

    @staticmethod
    def _context(path: str, tokenizer: Tokenizer, limit: int) -> str:
        """Cap context at one third of the input so body text always dominates."""
        if not path:
            return ""
        offsets = tokenizer.encode(path, add_special_tokens=False).offsets
        context_limit = max(1, limit // 3)
        if len(offsets) > context_limit:
            # Keep the topic and leaf title; full metadata remains on the chunk.
            half = max(1, (context_limit - 3) // 2)
            path = path[: offsets[half - 1][1]] + " ... " + path[offsets[-half][0] :]
        return f"{path}\n\n"


__all__ = ["KnowledgeChunker"]
