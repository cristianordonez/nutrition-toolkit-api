"""Regression cases for the layout patterns in the NCM and Diet Manual PDFs."""

from __future__ import annotations

import typing

import pytest
from tokenizers.models import WordPiece

from engine.models.knowledge import ExtractedKnowledgePage
from engine.pipelines.knowledge.ingestion.extractors.base import _outline_paths
from engine.pipelines.knowledge.ingestion.processing import (
    KnowledgeContentProcessor,
    chunker,
)
from engine.pipelines.knowledge.ingestion.processing.chunker import (
    KnowledgeChunker,
    _embedding_tokenizer,
)
from engine.pipelines.knowledge.ingestion.processing.section_parser import (
    KnowledgeStructureParser,
)
from engine.pipelines.knowledge.ingestion.processing.structure import (
    KnowledgeBlockType,
    KnowledgePageSpan,
    KnowledgeSection,
)

if typing.TYPE_CHECKING:
    from pathlib import Path

    from tokenizers import Tokenizer

pytestmark = pytest.mark.usefixtures("embedding_tokenizer")
_PATH = (
    "Nutrition Care",
    "Diabetes Mellitus",
    "Type 2 Diabetes",
    "Nutrition Assessment",
)
_TOKEN_LIMIT = 256
_FIRST_PAGE = 10
_LAST_PAGE = 11


def _page(
    number: int,
    text: str,
    path: tuple[str, ...] = _PATH,
) -> ExtractedKnowledgePage:
    return ExtractedKnowledgePage(page_number=number, text=text, section_path=path)


def test_dotted_outline_ignores_synthetic_title_and_retains_siblings() -> None:
    paths = _outline_paths(
        [
            [1, "Welcome", 1],
            [1, "Table of Contents", 2],
            [1, "Title", 4],
            [2, "Nutrition Care", 4],
            [1, "Title", 5],
            [2, "...Diabetes Mellitus", 5],
            [2, "......Type 2 Diabetes", 6],
            [2, ".........Nutrition Assessment", 7],
            [2, "............Food/Nutrition-Related History", 8],
            [2, "............Client History", 10],
            [2, ".........Nutrition Intervention", 11],
            [1, "Title", 12],
            [2, "...Metabolic Syndrome", 12],
            [2, "......Nutrition Intervention", 13],
        ],
        14,
    )

    assert paths[7] == _PATH
    assert paths[8] == paths[9] == (*_PATH, "Food/Nutrition-Related History")
    assert paths[10] == (*_PATH, "Client History")
    assert paths[11] == (*_PATH[:-1], "Nutrition Intervention")
    assert (
        paths[13]
        == paths[14]
        == ("Nutrition Care", "Metabolic Syndrome", "Nutrition Intervention")
    )


def test_standard_bookmarks_and_documents_without_bookmarks() -> None:
    assert _outline_paths([], 3) == {}
    assert _outline_paths(
        [
            [1, "Article", 1],
            [2, "First", 2],
            [2, "Second", 4],
        ],
        5,
    ) == {
        1: ("Article",),
        2: ("Article", "First"),
        3: ("Article", "First"),
        4: ("Article", "Second"),
        5: ("Article", "Second"),
    }


def test_html_entities_in_bookmarks_do_not_create_title_only_chunks() -> None:
    paths = _outline_paths([[1, "Preeclampsia &amp; Eclampsia", 1]], 1)
    assert paths[1] == ("Preeclampsia & Eclampsia",)
    assert (
        KnowledgeContentProcessor().build_chunks(
            [_page(1, "Preeclampsia & Eclampsia", paths[1])],
        )
        == []
    )


@pytest.mark.parametrize("path", [_PATH, ()])
@pytest.mark.parametrize("separator", ["\n", "\n\n"])
def test_wrapped_breadcrumb_is_not_a_standalone_chunk(
    path: tuple[str, ...],
    separator: str,
) -> None:
    text = (
        "Nutrition Care > Diabetes Mellitus > Type 2 Diabetes > Nutrition\nAssessment"
        + separator
        + "Nutrition Assessment"
        + separator
        + "Collect dietary history and interpret the assessment findings."
    )
    chunks = KnowledgeContentProcessor().build_chunks([_page(827, text, path)])
    assert len(chunks) == 1
    assert chunks[0].section_path == " > ".join(_PATH)
    assert chunks[0].section_title == "Nutrition Assessment"
    assert chunks[0].content == (
        " > ".join(_PATH)
        + "\n\nCollect dietary history and interpret the assessment findings."
    )


@pytest.mark.parametrize(
    "header",
    ["Nutrition Care > Diabetes > General Guidance", "> Diabetes > General Guidance"],
)
def test_empty_divider_pages_produce_no_chunks(header: str) -> None:
    assert (
        KnowledgeContentProcessor().build_chunks(
            [
                _page(
                    757,
                    header + "\n\nGeneral Guidance",
                    ("Nutrition Care", "Diabetes", "General Guidance"),
                ),
            ],
        )
        == []
    )


def test_subheadings_remain_body_text_not_ever_growing_breadcrumbs() -> None:
    path = ("Nutrition Care", "Metabolic Syndrome", "Nutrition Intervention")
    text = (
        "Nutrition Care > Metabolic Syndrome > Nutrition Intervention\n\n"
        "Nutrition Intervention\n\nReview the individual's goals.\n\n"
        "Self-monitoring\n\nRecord the agreed behaviors.\n\n"
        "Nutrition Education\n\nExplain the agreed plan.\n\n"
        "Nutrition Counseling\n\nReview barriers together."
    )
    chunks = KnowledgeContentProcessor().build_chunks([_page(1800, text, path)])
    assert len(chunks) == 1
    assert chunks[0].section_path == " > ".join(path)
    assert "Self-monitoring" in chunks[0].content
    assert "Nutrition Counseling" in chunks[0].content


def test_references_stay_excluded_across_pages_until_the_next_article() -> None:
    pages = [
        _page(
            1,
            "Nutrition Assessment\n\nKeep this assessment guidance.\n\n"
            "References\nA citation.",
        ),
        _page(
            2,
            "Nutrition Care > Diabetes Mellitus > Type 2 Diabetes > "
            "Nutrition Assessment\n\nNutrition Assessment\n\nNutrition Intervention\n"
            "A title-cased citation is not a new article.",
        ),
        _page(
            3,
            "Nutrition Intervention\n\nKeep this intervention guidance.",
            (*_PATH[:-1], "Nutrition Intervention"),
        ),
    ]
    chunks = KnowledgeContentProcessor().build_chunks(pages)
    assert [chunk.source_page_start for chunk in chunks] == [1, 3]
    assert all("citation" not in chunk.content for chunk in chunks)


@pytest.mark.parametrize(
    "title",
    [
        "Welcome",
        "Table of Contents",
        "Reviewers",
        "References: Diabetes",
        "Practice-Related Guidelines",
    ],
)
def test_non_content_articles_are_excluded(title: str) -> None:
    assert (
        KnowledgeContentProcessor().build_chunks(
            [
                _page(
                    1,
                    title + "\n\nThis is document navigation or citation metadata.",
                    (title,),
                ),
            ],
        )
        == []
    )


def test_split_line_table_of_contents_is_excluded_without_bookmarks() -> None:
    assert (
        KnowledgeContentProcessor().build_chunks(
            [
                _page(
                    2,
                    "Title\n4\n...Diet Liberalization\n5\n......Full Liquid Diet\n113",
                    (),
                ),
            ],
        )
        == []
    )


def test_numbers_and_comparisons_in_tables_are_not_discarded() -> None:
    chunks = KnowledgeContentProcessor().build_chunks(
        [
            _page(
                114,
                "Nutrition Assessment\n\nGlucose > 200 mg/dL\n\n"
                "Index\n21\nEnergy\n1200\nProtein\n60\n\nPage 114",
            ),
        ],
    )
    assert len(chunks) == 1
    assert "Glucose > 200 mg/dL" in chunks[0].content
    assert "1200" in chunks[0].content
    assert "60" in chunks[0].content
    assert "Index\n21" in chunks[0].content
    assert "Page 114" not in chunks[0].content


def test_continuation_pages_keep_article_and_precise_text_offsets() -> None:
    sections = KnowledgeStructureParser().parse(
        [
            _page(_FIRST_PAGE, "Nutrition Assessment\n\nFirst paragraph."),
            _page(_LAST_PAGE, "Second paragraph."),
        ],
    )
    assert len(sections) == 1
    assert sections[0].text == "First paragraph.\n\nSecond paragraph."
    for span in sections[0].page_spans:
        assert sections[0].text[span.start : span.end] in {
            "First paragraph.",
            "Second paragraph.",
        }
    assert sections[0].source_page_start == _FIRST_PAGE
    assert sections[0].source_page_end == _LAST_PAGE


def test_all_body_text_is_covered_and_total_tokens_fit_model(
    embedding_tokenizer: Tokenizer,
) -> None:
    text = " ".join(f"word{number}" for number in range(800))
    section = KnowledgeSection("Assessment", _PATH, text, 1, 1)
    chunks = KnowledgeChunker().chunk([section])
    recovered = {
        word for chunk in chunks for word in chunk.content.split("\n\n", 1)[1].split()
    }
    assert recovered == set(text.split())
    assert all(
        len(embedding_tokenizer.encode(chunk.content).ids) <= _TOKEN_LIMIT
        for chunk in chunks
    )
    assert all(chunk.content.startswith(" > ".join(_PATH)) for chunk in chunks)


def test_no_redundant_overlap_only_tail() -> None:
    text = " ".join("word" for _ in range(245))
    chunks = KnowledgeChunker().chunk([KnowledgeSection(None, (), text, 1, 1)])
    assert len(chunks) == 1
    assert chunks[0].content == text


def test_local_tokenizer_counts_without_saved_padding_or_truncation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    embedding_tokenizer: Tokenizer,
) -> None:
    embedding_tokenizer.enable_truncation(max_length=8)
    embedding_tokenizer.enable_padding(length=16)
    embedding_tokenizer.save(str(tmp_path / "tokenizer.json"))
    (tmp_path / "sentence_bert_config.json").write_text('{"max_seq_length": 256}')
    monkeypatch.setattr(chunker, "bundled_embedding_model_dir", lambda: tmp_path)

    # Exercise the real loader without adding test assets to its process cache.
    tokenizer, limit = _embedding_tokenizer.__wrapped__()

    assert limit == _TOKEN_LIMIT
    assert tokenizer.padding is None
    assert tokenizer.truncation is None
    assert len(tokenizer.encode("word " * 300).ids) > limit


def test_wordpiece_windows_preserve_text_and_fit_the_complete_input(
    embedding_tokenizer: Tokenizer,
) -> None:
    embedding_tokenizer.model = WordPiece(
        {"[UNK]": 0, "[CLS]": 1, "[SEP]": 2, "nutrition": 3, "##al": 4, "##ly": 5},
        unk_token="[UNK]",  # noqa: S106 - tokenizer marker, not a credential
    )
    text = "nutritionally " * 300
    chunks = KnowledgeChunker(overlap_tokens=0).chunk(
        [KnowledgeSection(None, (), text, 1, 1)],
    )

    assert "".join(chunk.content.replace(" ", "") for chunk in chunks) == (
        text.replace(" ", "")
    )
    assert all(
        len(embedding_tokenizer.encode(chunk.content).ids) <= _TOKEN_LIMIT
        for chunk in chunks
    )


def test_chunk_page_ranges_are_for_the_window_not_the_whole_article() -> None:
    first = " ".join("alpha" for _ in range(230))
    second = " ".join("beta" for _ in range(230))
    section = KnowledgeSection(
        "Assessment",
        _PATH,
        first + "\n\n" + second,
        10,
        11,
        page_spans=(
            KnowledgePageSpan(10, 0, len(first)),
            KnowledgePageSpan(11, len(first) + 2, len(first) + 2 + len(second)),
        ),
    )
    chunks = KnowledgeChunker().chunk([section])
    for chunk in chunks:
        body = chunk.content.split("\n\n", 1)[1]
        assert chunk.source_page_start == (10 if "alpha" in body else 11)
        assert chunk.source_page_end == (11 if "beta" in body else 10)


def test_oversized_context_cannot_crowd_out_body(
    embedding_tokenizer: Tokenizer,
) -> None:
    path = ("Nutrition Care", " ".join("long" for _ in range(500)), "Assessment")
    chunks = KnowledgeChunker().chunk(
        [
            KnowledgeSection(
                "Assessment",
                path,
                "Actual body guidance is retained.",
                1,
                1,
            ),
        ],
    )
    assert len(chunks) == 1
    assert chunks[0].section_path == " > ".join(path)
    assert "Actual body guidance" in chunks[0].content
    assert len(embedding_tokenizer.encode(chunks[0].content).ids) <= _TOKEN_LIMIT


@pytest.mark.parametrize("text", ["", "Assessment"])
def test_chunker_rejects_empty_or_title_only_sections(text: str) -> None:
    assert (
        KnowledgeChunker().chunk([KnowledgeSection("Assessment", (), text, 1, 1)]) == []
    )


def test_chunker_excludes_non_content_sections() -> None:
    section = KnowledgeSection(
        "References",
        (),
        "A long citation.",
        1,
        1,
        KnowledgeBlockType.REFERENCES,
    )
    assert KnowledgeChunker().chunk([section]) == []
