from __future__ import annotations

import pathlib


def _index() -> str:
    return (pathlib.Path(__file__).parents[3] / "src/ntk/static/index.html").read_text(
        encoding="utf-8",
    )


def test_index_exposes_nutrition_care_process_upload_workflow() -> None:
    index = _index()

    assert "Nutrition Care Process" in index
    assert "nutrition diagnosis, intervention, and monitoring &amp; evaluation" in index
    assert 'id="demo-form"' in index
    assert 'id="drop-zone"' in index
    assert 'id="clinical-file"' in index
    assert 'name="files" type="file"' in index
    assert 'name="files" type="file" accept=' in index
    assert "multiple required" in index
    assert "application/pdf,text/csv,text/plain" in index
    assert "/api/v1/demo/assessment" in index
    assert 'data.append("files", file)' in index
    assert 'id="ingest-form"' not in index
    assert "/api/v1/knowledge/ingest" not in index


def test_index_sends_api_key_without_browser_storage() -> None:
    index = _index()

    assert 'id="api-key" type="password"' in index
    assert 'headers.set("Authorization", `Bearer ${apiKey}`)' in index
    assert "localStorage" not in index
    assert "sessionStorage" not in index
    assert index.count("return fetch(") == 1


def test_index_displays_timed_ncp_generation_without_fake_backend_telemetry() -> None:
    index = _index()

    assert 'id="processing-screen"' in index
    assert "Generating Nutrition Care Process" in index
    assert "Preparing clinical information" in index
    assert "Reviewing nutrition history and relevant data" in index
    assert "Analyzing assessment and nutrition diagnosis" in index
    assert "Developing interventions and monitoring plan" in index
    assert "Finalizing Nutrition Care Process" in index
    assert "they do not represent live backend completion" in index
    assert "generationStages" in index
    assert "clearGenerationTimers" in index
    assert 'window.addEventListener("pagehide", clearGenerationTimers)' in index
    assert "Generating for ${elapsed}s" in index
    assert "% complete" not in index
    assert "response.ingestion.facts_extracted" in index
    assert "response.context.raw_token_count" in index
    assert "response.context.final_token_count" in index
    assert "response.context.token_reduction_percent" in index


def test_index_prevents_duplicate_generation_and_preserves_inputs_on_failure() -> None:
    index = _index()

    assert "if (state.generating) return;" in index
    assert "generateButton.disabled = busy" in index
    assert "fileInput.disabled = busy" in index
    assert 'textContent = busy ? "Generating…"' in index
    assert "generationErrorMessage(error)" in index
    assert "Unable to generate the Nutrition Care Process. Please try again." in index


def test_index_renders_person_detail_as_clinical_snapshot() -> None:
    index = _index()

    assert 'id="clinical-snapshot"' in index
    assert "detail.current_weight" in index
    assert "detail.current_diet" in index
    assert "detail.meal_intakes" in index
    assert "detail.active_supplements" in index
    assert "detail.labs" in index
    assert "detail.wounds" in index
    assert "detail.active_diagnoses" in index
    assert "No structured nutrition details were returned." in index


def test_index_includes_assessment_evidence_and_real_actions() -> None:
    index = _index()

    assert 'id="assessment-content"' in index
    assert "Assessment & nutrition diagnosis" in index
    assert "Monitoring & evaluation" in index
    assert 'id="evidence-dialog"' in index
    assert "View supporting data" in index
    assert 'id="details-dialog"' in index
    assert "ContextBudgeter optimization" in index
    assert 'method: "PATCH"' in index
    assert "/api/v1/assessments/${assessmentId}/finalize" in index
    assert 'id="copy-button"' in index
    assert 'id="edit-button"' in index
    assert 'id="regenerate-button"' in index
    assert 'id="start-over-button"' in index


def test_index_is_responsive_and_accessible() -> None:
    index = _index()

    assert "@media (max-width: 900px)" in index
    assert "@media (max-width: 620px)" in index
    assert "@media (prefers-reduced-motion: reduce)" in index
    assert 'aria-live="polite"' in index
    assert 'role="alert"' in index
    assert '<dialog id="evidence-dialog"' in index
    assert 'for="clinical-file"' in index


def test_index_provides_four_shared_feature_tabs() -> None:
    index = _index()

    assert 'aria-label="Primary features"' in index
    assert 'data-feature-tab="ncp"' in index
    assert 'data-feature-tab="energy"' in index
    assert 'data-feature-tab="tube-feed"' in index
    assert 'data-feature-tab="knowledge"' in index
    assert 'id="energy-form"' in index
    assert 'id="tube-feed-form"' in index
    assert 'id="knowledge-form"' in index


def test_index_uses_existing_calculation_and_search_apis() -> None:
    index = _index()

    assert "calculateEnergyNeeds(payload)" in index
    assert '"/api/v1/calculate/"' in index
    assert "calculateTubeFeed(payload)" in index
    assert '"/api/v1/calculate/tubefeed"' in index
    assert "searchKnowledge(payload)" in index
    assert '"/api/v1/knowledge/search"' in index
    assert "payload.document_type = source" in index
    assert '<option value="diet-manual">Diet Manual</option>' in index
    assert (
        '<option value="nutrition-care-manual">Nutrition Care Manual</option>' in index
    )
