from __future__ import annotations

import asyncio
import typing

import httpx
import pytest

from engine.clients.cloud_api_client import CloudAPIClient

Handler = typing.Callable[[httpx.Request], httpx.Response]

_NCP = {
    "id": 31,
    "person_identifier": "EN140472",
    "note_text": "Nutrition Follow Up",
    "content_hash": "hash",
    "created_by": "model",
    "status": "draft",
    "created_at": "2026-09-21T00:00:00Z",
}


@pytest.fixture
def capture(
    monkeypatch: pytest.MonkeyPatch,
) -> typing.Callable[[], list[httpx.Request]]:
    """Serve every request locally, recording what was sent."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        payload = _NCP if request.url.path.endswith("/generate") else [_NCP]
        return httpx.Response(200, json=payload)

    transport = httpx.MockTransport(handler)
    original = httpx.AsyncClient

    def patched(**kwargs: object) -> httpx.AsyncClient:
        kwargs.pop("transport", None)
        return original(transport=transport, **kwargs)  # ty: ignore[invalid-argument-type]

    monkeypatch.setattr(httpx, "AsyncClient", patched)
    return lambda: seen


def test_generate_sends_the_bearer_token(
    capture: typing.Callable[[], list[httpx.Request]],
) -> None:
    """Every NCP route is behind require_any_permission, so this must be sent."""
    client = CloudAPIClient("http://localhost:8000", api_key="secret-key")

    asyncio.run(client.list_ncps("EN140472"))

    request = capture()[0]
    assert request.headers["authorization"] == "Bearer secret-key"


def test_no_authorization_header_when_no_key_is_configured(
    capture: typing.Callable[[], list[httpx.Request]],
) -> None:
    client = CloudAPIClient("http://localhost:8000")

    asyncio.run(client.list_ncps("EN140472"))

    assert "authorization" not in capture()[0].headers


def test_generate_still_declares_json_content_type(
    capture: typing.Callable[[], list[httpx.Request]],
) -> None:
    client = CloudAPIClient("http://localhost:8000", api_key="secret-key")

    ncp = asyncio.run(
        client.generate_ncp(
            typing.cast(
                "typing.Any",
                _StubRequest(),
            ),
        ),
    )

    request = capture()[0]
    assert request.headers["content-type"] == "application/json"
    assert request.headers["authorization"] == "Bearer secret-key"
    assert ncp.person_identifier == "EN140472"


class _StubRequest:
    """Minimal stand-in for a generation request."""

    @staticmethod
    def model_dump_json() -> str:
        return '{"person_identifier": "EN140472"}'
