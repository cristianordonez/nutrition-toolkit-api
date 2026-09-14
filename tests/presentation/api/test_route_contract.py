from __future__ import annotations

from fastapi.routing import APIRoute

from ntk.presentation.api.routers import (
    documents,
    knowledge,
    nutrition_care_processes,
    persons,
)


def test_requested_route_contract_is_registered() -> None:
    routes = {
        (route.path, method)
        for module in (persons, knowledge, documents, nutrition_care_processes)
        for route in module.router.routes
        if isinstance(route, APIRoute)
        for method in route.methods or set()
    }
    expected = {
        ("/persons/", "GET"),
        ("/persons/{person_id}", "GET"),
        ("/persons/{person_id}/nutrition-care-processes", "GET"),
        ("/persons/{person_id}/weights", "GET"),
        ("/persons/{person_id}/clinical-facts", "GET"),
        ("/knowledge/search", "POST"),
        ("/nutrition-care-processes/search", "POST"),
        ("/document/ingest", "POST"),
        ("/nutrition-care-processes/import", "POST"),
        ("/nutrition-care-processes/sync", "POST"),
        ("/nutrition-care-processes/generate", "POST"),
        ("/nutrition-care-processes", "GET"),
        ("/nutrition-care-processes/{ncp_id}", "GET"),
        ("/nutrition-care-processes/{ncp_id}", "PATCH"),
        ("/nutrition-care-processes/{ncp_id}/finalize", "POST"),
    }

    assert expected <= routes


def test_superseded_routes_are_removed() -> None:
    paths = {
        route.path
        for module in (persons, knowledge, documents, nutrition_care_processes)
        for route in module.router.routes
        if isinstance(route, APIRoute)
    }

    assert "/persons/generate" not in paths
    assert "/search/assessment" not in paths
    assert "/search/nutrition-care-processes" not in paths
    assert "/search/knowledge" not in paths
    assert "/documents/ingestion" not in paths
    assert "/nutrition-care-processes/ingestion" not in paths
