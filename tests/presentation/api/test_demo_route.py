from __future__ import annotations

import asyncio
import typing
from types import SimpleNamespace

import pytest
from fastapi.routing import APIRoute
from pydantic_ai.exceptions import ModelAPIError

from ntk.pipelines.demo import NoDemoFactsError
from ntk.presentation.api.routers import demo

if typing.TYPE_CHECKING:
    from fastapi import UploadFile


class Upload:
    filename = "orders.pdf"

    async def read(self) -> bytes:
        return b"pdf"


@pytest.mark.parametrize(
    "exception",
    [
        NoDemoFactsError("none"),
        ValueError("invalid upload"),
    ],
)
def test_demo_route_maps_invalid_transient_inputs(
    exception: ValueError,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_file_count = 2

    class Controller:
        def __init__(self, session: object) -> None:
            assert session == "session"

        @staticmethod
        async def run(options: object) -> object:
            assert len(options.files) == expected_file_count  # ty: ignore[unresolved-attribute]
            raise exception

    monkeypatch.setattr(demo, "DemoAssessmentController", Controller)
    with pytest.raises(demo.HTTPException) as error:
        asyncio.run(
            demo.generate_demo_assessment(
                typing.cast("list[UploadFile]", [Upload(), Upload()]),
                "session",  # ty: ignore[invalid-argument-type]
            ),
        )

    assert error.value.status_code == 422  # noqa: PLR2004


def test_demo_route_returns_combined_controller_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = SimpleNamespace(assessment="combined")
    expected_file_count = 2

    class Controller:
        def __init__(self, session: object) -> None:
            assert session == "session"

        @staticmethod
        async def run(options: object) -> object:
            assert len(options.files) == expected_file_count  # ty: ignore[unresolved-attribute]
            return SimpleNamespace(result=expected)

    monkeypatch.setattr(demo, "DemoAssessmentController", Controller)

    result = asyncio.run(
        demo.generate_demo_assessment(
            typing.cast("list[UploadFile]", [Upload(), Upload()]),
            "session",  # ty: ignore[invalid-argument-type]
        ),
    )

    assert result is expected


@pytest.mark.parametrize(
    "exception",
    [
        ConnectionError("connection failed"),
        ModelAPIError("test-model", "connection failed"),
    ],
)
def test_demo_route_maps_ai_connection_errors_to_service_unavailable(
    exception: Exception,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Controller:
        @staticmethod
        async def run(_options: object) -> object:
            raise exception

    monkeypatch.setattr(demo, "DemoAssessmentController", lambda _session: Controller())

    with pytest.raises(demo.HTTPException) as error:
        asyncio.run(
            demo.generate_demo_assessment(
                typing.cast("list[UploadFile]", [Upload()]),
                "session",  # ty: ignore[invalid-argument-type]
            ),
        )

    assert error.value.status_code == 503  # noqa: PLR2004
    assert "AI provider unavailable" in error.value.detail


def test_demo_router_exposes_assessment_endpoint() -> None:
    paths = {route.path for route in demo.router.routes if isinstance(route, APIRoute)}

    assert "/demo/assessment" in paths
