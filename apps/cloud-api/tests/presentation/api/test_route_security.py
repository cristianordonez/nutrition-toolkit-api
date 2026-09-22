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
    ("knowledge", "/knowledge/ingest", "knowledge:write", 50, "knowledge-ingest"),
    (
        "knowledge",
        "/knowledge/search",
        "knowledge:read",
        60,
        "search-knowledge",
    ),
    (
        "nutrition_care_processes",
        "/nutrition-care-processes/search",
        "ncp:read",
        60,
        "search-ncps",
    ),
    (
        "nutrition_care_processes",
        "/nutrition-care-processes",
        "ncp:read",
        60,
        "ncps-list",
    ),
    (
        "nutrition_care_processes",
        "/nutrition-care-processes/{ncp_id}",
        "ncp:read",
        60,
        "ncps-get",
    ),
    (
        "nutrition_care_processes",
        "/nutrition-care-processes/{ncp_id}/finalize",
        "ncp:write",
        30,
        "ncps-finalize",
    ),
    (
        "nutrition_care_processes",
        "/nutrition-care-processes/{ncp_id}",
        "ncp:write",
        30,
        "ncps-update",
    ),
    (
        "nutrition_care_processes",
        "/nutrition-care-processes/generate",
        "ncp:write",
        25,
        "ncps-generate",
    ),
    (
        "nutrition_care_processes",
        "/nutrition-care-processes/sync",
        "ncp:write",
        20,
        "ncps-sync",
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
        f"api.presentation.api.routers.{module_name}",
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
