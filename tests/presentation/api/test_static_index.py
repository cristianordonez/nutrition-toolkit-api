from __future__ import annotations

import pathlib


def test_ingest_form_sends_api_key_as_bearer_token() -> None:
    index = (pathlib.Path(__file__).parents[3] / "src/ntk/static/index.html").read_text(
        encoding="utf-8",
    )

    assert 'id="api-key" type="password"' in index
    assert 'headers.set("Authorization", `Bearer ${apiKey}`)' in index
    assert "localStorage" not in index
    assert "sessionStorage" not in index
    assert index.count("return fetch(") == 1
    assert index.count("await authorizedFetch(") == 6  # noqa: PLR2004


def test_index_includes_knowledge_ingest_and_search_forms() -> None:
    index = (pathlib.Path(__file__).parents[3] / "src/ntk/static/index.html").read_text(
        encoding="utf-8",
    )

    assert 'id="search-text"' in index
    assert 'id="ingest-form"' in index
    assert "/api/v1/knowledge/ingest" in index
    assert 'name="top_k"' in index
    assert 'min="1" max="20"' in index
    assert "/api/v1/knowledge/search" in index
    assert "result?.chunk_count" in index
    assert "Array.isArray(knowledge.chunks) ? knowledge.chunks.length : 0" in index
    assert "document.chunk_count" not in index


def test_index_includes_assessment_workflows() -> None:
    index = (pathlib.Path(__file__).parents[3] / "src/ntk/static/index.html").read_text(
        encoding="utf-8",
    )

    assert 'id="assessment-form"' in index
    assert 'id="assessment-files"' in index
    assert (
        'name="files" type="file" '
        'accept="application/pdf,text/csv,.pdf,.csv" multiple' in index
    )
    assert "body.content" in index
    assert 'id="assessment-file-summary"' in index
    assert "/api/v1/assessment/generate" in index
    assert 'id="assessment-ingest-form"' in index
    assert 'id="assessment-ingest-files"' in index
    assert "assessmentIngestFiles.files.length" in index
    assert "assessment${assessmentCount" in index
    assert "ingested from ${fileCount} file" in index
    assert "alert(message)" in index
    assert 'name="created_by"' in index
    assert "/api/v1/assessment/ingest" in index
    assert 'id="assessment-search-form"' in index
    assert 'id="assessment-search-text"' in index
    assert 'id="assessment-search-results"' in index
    assert "/api/v1/assessment/search" in index


def test_index_includes_resident_extract_workflow() -> None:
    index = (pathlib.Path(__file__).parents[3] / "src/ntk/static/index.html").read_text(
        encoding="utf-8",
    )

    assert 'id="resident-extract-form"' in index
    assert 'id="resident-extract-files"' in index
    assert 'name="context"' in index
    assert "/api/v1/resident/extract" in index
    assert "JSON.stringify(body, null, 2)" in index
    assert 'id="resident-extract-output"' in index
