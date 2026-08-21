from __future__ import annotations

import pathlib


def test_ingest_form_does_not_expose_api_keys() -> None:
    index = (pathlib.Path(__file__).parents[3] / "src/ntk/static/index.html").read_text(
        encoding="utf-8",
    )

    assert 'id="api-key"' not in index
    assert "Authorization" not in index


def test_index_includes_rag_search_form() -> None:
    index = (pathlib.Path(__file__).parents[3] / "src/ntk/static/index.html").read_text(
        encoding="utf-8",
    )

    assert 'id="search-text"' in index
    assert 'name="top_k"' in index
    assert 'min="1" max="20"' in index
    assert "/api/v1/rag/search" in index


def test_index_includes_assessment_form() -> None:
    index = (pathlib.Path(__file__).parents[3] / "src/ntk/static/index.html").read_text(
        encoding="utf-8",
    )

    assert 'id="assessment-form"' in index
    assert 'id="assessment-files"' in index
    assert 'name="files" type="file" accept="application/pdf,.pdf" multiple' in index
    assert 'id="assessment-file-summary"' in index
    assert "/api/v1/assessment" in index
