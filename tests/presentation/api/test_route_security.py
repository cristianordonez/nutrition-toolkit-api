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
    ("knowledge", "/knowledge/search", "knowledge:read", 60, "knowledge-search"),
    ("knowledge", "/knowledge/ingest", "knowledge:write", 50, "knowledge-ingest"),
    (
        "assessment",
        "/assessment/generate",
        "assessments:write",
        10,
        "assessment-generate",
    ),
    (
        "assessment",
        "/assessment/ingest",
        "assessments:write",
        20,
        "assessment-ingest",
    ),
    (
        "assessment",
        "/assessment/search",
        "assessments:read",
        60,
        "assessment-search",
    ),
    ("resident", "/resident/extract", "residents:read", 40, "resident-extract"),
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
    route = next(
        typing.cast("APIRoute", item)
        for item in module.router.routes
        if item.path == path
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
