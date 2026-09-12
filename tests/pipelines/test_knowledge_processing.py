"""Tests for deterministic knowledge cleanup and provenance-aware chunking."""

from __future__ import annotations

import typing

from ntk.models.knowledge import ExtractedKnowledgePage, KnowledgeSectionType
from ntk.pipelines.knowledge.ingestion import processing
from ntk.pipelines.knowledge.ingestion.processing import KnowledgeContentProcessor

if typing.TYPE_CHECKING:
    import pytest

_SOURCE_PAGE = 7


def test_classifies_only_explicit_non_content_headings() -> None:
    classify = KnowledgeContentProcessor.classify_heading

    assert classify("References: Regulations") is KnowledgeSectionType.REFERENCES
    assert classify("Selected References") is KnowledgeSectionType.REFERENCES
    assert classify("Table of Contents") is KnowledgeSectionType.TABLE_OF_CONTENTS
    assert classify("Contributors") is KnowledgeSectionType.METADATA
    assert classify("The guidance references current regulations.") is None


def test_cleanup_embeds_only_substantive_page_content_with_provenance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages = [
        ExtractedKnowledgePage(
            page_number=1,
            text=(
                "Nutrition Care Manual\n"
                "Table of Contents\n"
                "Full Liquid Diet ........ 113\n"
                "Consistent Carbohydrate Diet ........ 114\n"
                "Copyright 2026 Academy of Nutrition and Dietetics\n"
                "Page 1"
            ),
        ),
        ExtractedKnowledgePage(
            page_number=113,
            text=(
                "Nutrition Care Manual\n"
                "Full Liquid Diet\n"
                "Definition:\n"
                "The full liquid diet supports individualized care (Dorner, 2018).\n"
                "References\n"
                "Dorner B, Friedrich EK. Position on weight loss and aging.\n"
                "J Acad Nutr Diet. 2018;118:604-609.\n"
                "Copyright 2026 Academy of Nutrition and Dietetics\n"
                "Page 113"
            ),
        ),
        ExtractedKnowledgePage(
            page_number=114,
            text=(
                "Nutrition Care Manual\n"
                "Consistent Carbohydrate Diet\n"
                "Definition:\n"
                "Carbohydrate intake is distributed consistently across meals.\n"
                "Page 114"
            ),
        ),
        ExtractedKnowledgePage(
            page_number=118,
            text=(
                "Nutrition Care Manual\n"
                "Reviewers\n"
                "Jane Dietitian, RDN\n"
                "John Reviewer, MS\n"
                "Heart-Healthy Diet\n"
                "Definition:\n"
                "Emphasize fruits, vegetables, and unsaturated fats.\n"
                "Page 118"
            ),
        ),
    ]
    monkeypatch.setattr(processing, "sliding_window", lambda text: [text])

    chunks = KnowledgeContentProcessor().build_chunks(pages)

    assert [chunk.section_title for chunk in chunks] == [
        "Full Liquid Diet",
        "Consistent Carbohydrate Diet",
        "Heart-Healthy Diet",
    ]
    assert [chunk.source_page_start for chunk in chunks] == [113, 114, 118]
    assert all(chunk.source_page_start == chunk.source_page_end for chunk in chunks)
    embedded_text = "\n".join(chunk.content for chunk in chunks)
    assert "Full Liquid Diet\nDefinition:" in embedded_text
    assert "(Dorner, 2018)" in embedded_text
    assert "Position on weight loss" not in embedded_text
    assert "Full Liquid Diet ........ 113" not in embedded_text
    assert "Jane Dietitian" not in embedded_text
    assert "Copyright" not in embedded_text
    assert "Page 113" not in embedded_text
    assert "Nutrition Care Manual" not in embedded_text


def test_section_title_is_prepended_to_every_chunk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages = [
        ExtractedKnowledgePage(
            page_number=_SOURCE_PAGE,
            text="Renal Diet\nDefinition:\nFirst guidance.\nSecond guidance.",
        ),
    ]
    monkeypatch.setattr(
        processing,
        "sliding_window",
        lambda _text: ["Renal Diet\nDefinition:\nFirst guidance.", "Second guidance."],
    )

    chunks = KnowledgeContentProcessor().build_chunks(pages)

    assert chunks[0].content.startswith("Renal Diet\n")
    assert chunks[1].content == "Renal Diet\n\nSecond guidance."
    assert chunks[1].source_page_start == _SOURCE_PAGE
    assert chunks[1].source_page_end == _SOURCE_PAGE
