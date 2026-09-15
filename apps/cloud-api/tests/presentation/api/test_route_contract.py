from __future__ import annotations

from fastapi.routing import APIRoute

from api.presentation.api.routers import knowledge, nutrition_care_processes


def test_requested_route_contract_is_registered() -> None:
    routes = {
        (route.path, method)
        for module in (knowledge, nutrition_care_processes)
        for route in module.router.routes
        if isinstance(route, APIRoute)
        for method in route.methods or set()
    }
    expected = {
        ("/knowledge/ingest", "POST"),
        ("/knowledge/search", "POST"),
        ("/nutrition-care-processes", "GET"),
        ("/nutrition-care-processes/{ncp_id}", "GET"),
        ("/nutrition-care-processes/{ncp_id}", "PATCH"),
        ("/nutrition-care-processes/{ncp_id}/finalize", "POST"),
        ("/nutrition-care-processes/sync", "POST"),
        ("/nutrition-care-processes/generate", "POST"),
        ("/nutrition-care-processes/search", "POST"),
    }

    assert expected <= routes


def test_superseded_routes_are_removed() -> None:
    paths = {
        route.path
        for module in (knowledge, nutrition_care_processes)
        for route in module.router.routes
        if isinstance(route, APIRoute)
    }

    assert "/persons/generate" not in paths
    assert "/search/assessment" not in paths
    assert "/search/nutrition-care-processes" not in paths
    assert "/search/knowledge" not in paths
    assert "/documents/ingestion" not in paths
    assert "/nutrition-care-processes/ingestion" not in paths
    assert "/nutrition-care-processes/import" not in paths
    assert "/document/ingest" not in paths
