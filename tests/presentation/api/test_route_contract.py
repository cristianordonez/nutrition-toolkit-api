from __future__ import annotations

from fastapi.routing import APIRoute

from ntk.presentation.api.routers import assessments, documents, residents, search


def test_requested_route_contract_is_registered() -> None:
    routes = {
        (route.path, method)
        for module in (residents, search, documents, assessments)
        for route in module.router.routes
        if isinstance(route, APIRoute)
        for method in route.methods or set()
    }
    expected = {
        ("/residents/", "GET"),
        ("/residents/{resident_id}/assessments", "GET"),
        ("/residents/{resident_id}/weights", "GET"),
        ("/residents/{resident_id}/clinical-facts", "GET"),
        ("/search/knowledge", "POST"),
        ("/search/assessments", "POST"),
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
        for module in (residents, search, documents, assessments)
        for route in module.router.routes
        if isinstance(route, APIRoute)
    }

    assert "/residents/generate" not in paths
    assert "/search/assessment" not in paths
    assert "/documents/ingestion" not in paths
    assert "/assessments/ingestion" not in paths
