from __future__ import annotations

import inspect
import typing

import pytest

if typing.TYPE_CHECKING:
    import types
    from collections.abc import Callable

    from fastapi.routing import APIRoute

_ROUTE_POLICIES = [
    ("calculate", "/calculate/", "calculate:read", 120, "calculate-energy"),
    (
        "calculate",
        "/calculate/tubefeed",
        "calculate:read",
        120,
        "calculate-tubefeed",
    ),
    ("knowledge", "/knowledge/ingest", "knowledge:write", 50, "knowledge-ingest"),
    ("residents", "/residents/", "residents:read", 60, "residents-list"),
    (
        "residents",
        "/residents/{resident_id}/assessments",
        "assessments:read",
        60,
        "residents-assessments",
    ),
    (
        "residents",
        "/residents/{resident_id}/weights",
        "residents:read",
        60,
        "residents-weights",
    ),
    (
        "residents",
        "/residents/{resident_id}/clinical-facts",
        "residents:read",
        60,
        "residents-clinical-facts",
    ),
    (
        "search",
        "/search/knowledge",
        "knowledge:read",
        60,
        "search-knowledge",
    ),
    (
        "search",
        "/search/assessments",
        "assessments:read",
        60,
        "search-assessments",
    ),
    (
        "documents",
        "/document/ingest",
        "residents:write",
        40,
        "document-ingest",
    ),
    (
        "assessments",
        "/assessments",
        "assessments:read",
        60,
        "assessments-list",
    ),
    (
        "assessments",
        "/assessments/{assessment_id}",
        "assessments:read",
        60,
        "assessments-get",
    ),
    (
        "assessments",
        "/assessments/{assessment_id}/finalize",
        "assessments:write",
        30,
        "assessments-finalize",
    ),
    (
        "assessments",
        "/assessments/{assessment_id}",
        "assessments:write",
        30,
        "assessments-update",
    ),
    (
        "assessments",
        "/assessments/generate",
        "assessments:write",
        25,
        "assessments-generate",
    ),
    (
        "assessments",
        "/assessments/import",
        "assessments:write",
        20,
        "assessments-import",
    ),
]


@pytest.mark.parametrize(
    "policy",
    _ROUTE_POLICIES,
)
def test_route_requires_permission_and_rate_limit(
    policy: tuple[str, str, str, int, str],
    load_controller_module: Callable[[str], types.ModuleType],
) -> None:
    module_name, path, permission, limit, scope = policy
    module = load_controller_module(
        f"ntk.presentation.api.routers.{module_name}",
    )
    matching_routes = [
        typing.cast("APIRoute", item)
        for item in module.router.routes
        if item.path == path
    ]
    route = next(
        item
        for item in matching_routes
        if any(
            inspect.getclosurevars(dependency.call).nonlocals.get("scope") == scope
            for dependency in item.dependant.dependencies  # codespell:ignore dependant
            if dependency.call is not None
        )
    )
    closures = {
        getattr(dependency.call, "__name__", ""): inspect.getclosurevars(
            dependency.call,
        ).nonlocals
        for dependency in route.dependant.dependencies  # codespell:ignore dependant
        if dependency.call is not None
    }
    assert closures["permission_checker"]["permissions"] == ["admin", permission]
    assert closures["rate_limiter"]["limit"] == limit
    assert closures["rate_limiter"]["window"] == 3600  # noqa: PLR2004
    assert closures["rate_limiter"]["scope"] == scope
