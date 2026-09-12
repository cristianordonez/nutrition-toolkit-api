from __future__ import annotations

from fastapi.routing import APIRoute

from ntk.presentation.api.routers import assessments, documents, knowledge, persons


def test_requested_route_contract_is_registered() -> None:
    routes = {
        (route.path, method)
        for module in (persons, knowledge, documents, assessments)
        for route in module.router.routes
        if isinstance(route, APIRoute)
        for method in route.methods or set()
    }
    expected = {
        ("/persons/", "GET"),
        ("/persons/{person_id}", "GET"),
        ("/persons/{person_id}/assessments", "GET"),
        ("/persons/{person_id}/weights", "GET"),
        ("/persons/{person_id}/clinical-facts", "GET"),
        ("/knowledge/search", "POST"),
        ("/assessments/search", "POST"),
        ("/document/ingest", "POST"),
        ("/assessments/import", "POST"),
        ("/assessments/sync", "POST"),
        ("/assessments/generate", "POST"),
        ("/assessments", "GET"),
        ("/assessments/{assessment_id}", "GET"),
        ("/assessments/{assessment_id}", "PATCH"),
        ("/assessments/{assessment_id}/finalize", "POST"),
    }

    assert expected <= routes


def test_superseded_routes_are_removed() -> None:
    paths = {
        route.path
        for module in (persons, knowledge, documents, assessments)
        for route in module.router.routes
        if isinstance(route, APIRoute)
    }

    assert "/persons/generate" not in paths
    assert "/search/assessment" not in paths
    assert "/search/assessments" not in paths
    assert "/search/knowledge" not in paths
    assert "/documents/ingestion" not in paths
    assert "/assessments/ingestion" not in paths
