from __future__ import annotations

import asyncio
import json
import typing

import httpx
import pytest

from engine.clients.ollama_client import OllamaClient, OllamaUnavailableError

Handler = typing.Callable[[httpx.Request], httpx.Response]

_CATALOG = {"models": [{"name": "qwen2.5:14b"}, {"name": "llama3.2:latest"}]}


@pytest.fixture
def serve(monkeypatch: pytest.MonkeyPatch) -> typing.Callable[[Handler], OllamaClient]:
    """Return a factory for clients whose HTTP calls a handler answers."""

    def factory(handler: Handler) -> OllamaClient:
        transport = httpx.MockTransport(handler)
        original = httpx.AsyncClient

        def patched(**kwargs: object) -> httpx.AsyncClient:
            kwargs.pop("transport", None)
            return original(transport=transport, **kwargs)  # ty: ignore[invalid-argument-type]

        monkeypatch.setattr(httpx, "AsyncClient", patched)
        return OllamaClient("http://localhost:11434")

    return factory


def _catalog(_request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json=_CATALOG)


def test_is_available_is_false_when_the_daemon_is_down(
    serve: typing.Callable[[Handler], OllamaClient],
) -> None:
    def refuse(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    assert asyncio.run(serve(refuse).is_available()) is False


def test_list_models_returns_names(
    serve: typing.Callable[[Handler], OllamaClient],
) -> None:
    assert asyncio.run(serve(_catalog).list_models()) == [
        "qwen2.5:14b",
        "llama3.2:latest",
    ]


@pytest.mark.parametrize(
    ("wanted", "expected"),
    [
        ("qwen2.5:14b", True),
        # A bare name means the "latest" tag, which is how Ollama reports it.
        ("llama3.2", True),
        ("qwen2.5:32b", False),
    ],
)
def test_has_model_matches_bare_and_tagged_names(
    serve: typing.Callable[[Handler], OllamaClient],
    wanted: str,
    expected: bool,  # noqa: FBT001 - pytest.mark.parametrize supplies it
) -> None:
    assert asyncio.run(serve(_catalog).has_model(wanted)) is expected


def test_pull_reports_progress_and_ignores_malformed_lines(
    serve: typing.Callable[[Handler], OllamaClient],
) -> None:
    lines = [
        json.dumps({"status": "pulling", "completed": 1, "total": 4}),
        "not json",
        "",
        json.dumps({"status": "success", "completed": 4, "total": 4}),
    ]

    def stream(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="\n".join(lines))

    seen: list[tuple[str, int, int]] = []
    asyncio.run(
        serve(stream).pull(
            "qwen2.5:14b",
            on_progress=lambda *event: seen.append(event),
        ),
    )

    assert seen == [("pulling", 1, 4), ("success", 4, 4)]


def test_pull_surfaces_a_daemon_error(
    serve: typing.Callable[[Handler], OllamaClient],
) -> None:
    def failing(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=json.dumps({"error": "model not found"}))

    with pytest.raises(OllamaUnavailableError, match="model not found"):
        asyncio.run(serve(failing).pull("nope:1b"))
