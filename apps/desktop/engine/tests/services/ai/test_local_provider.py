from __future__ import annotations

import asyncio
import json
import logging
import typing

import httpx2
import pytest
from pydantic import BaseModel

from engine.models.ai import AIProvider, AIStatusValue
from engine.models.settings import LocalAISettings
from engine.services.ai.controller import AIController
from engine.services.ai.errors import (
    AIStructuredOutputError,
    LocalAITimeoutError,
    LocalAIUnavailableError,
    ProviderConfigurationError,
)
from engine.services.ai.local_provider import (
    LocalAIProvider,
    LocalJsonSchemaTransformer,
    validate_local_url,
)
from engine.services.ai.openai_provider import OpenAIProvider

#: Stand in for clinical content; must never reach a log or an error.
PHI_PROMPT = "Resident Jane Example has a stage 3 sacral wound"
PHI_REPLY = "Assessment for Jane Example: increase protein"


class _Probe(BaseModel):
    word: typing.Literal["OK"]
    number: int


def _settings(**values: typing.Any) -> LocalAISettings:  # noqa: ANN401
    return LocalAISettings(_env_file=None, **values)  # ty: ignore[unknown-argument]


def _completion(content: str) -> dict[str, object]:
    return {
        "id": "chatcmpl-1",
        "object": "chat.completion",
        "created": 0,
        "model": "local",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            },
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


def _provider(
    handler: typing.Callable[[httpx2.Request], httpx2.Response],
    **values: typing.Any,  # noqa: ANN401
) -> LocalAIProvider:
    return LocalAIProvider(
        _settings(**values),
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)),
    )


def _through_controller(provider: LocalAIProvider) -> AIController:
    return AIController(
        provider,
        OpenAIProvider(token=lambda: "unused"),
        selected=lambda: AIProvider.LOCAL,
    )


def test_the_default_endpoint_is_localhost_8080() -> None:
    assert LocalAIProvider(_settings()).base_url == "http://127.0.0.1:8080"


def test_nutrition_ai_llama_url_sets_the_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NUTRITION_AI_LLAMA_URL", "http://localhost:9090/")

    assert LocalAIProvider(LocalAISettings(_env_file=None)).base_url == (  # ty: ignore[unknown-argument]
        "http://localhost:9090"
    )


def test_sends_a_chat_request_to_the_configured_endpoint() -> None:
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(200, json=_completion("OK."))

    provider = _provider(
        handler,
        llama_url="http://127.0.0.1:8081",
        llama_api_key="session-key",
        temperature=0.2,
        max_tokens=64,
    )

    reply = asyncio.run(_through_controller(provider).chat("Respond with OK."))

    assert reply == "OK."
    request = seen[0]
    assert str(request.url) == "http://127.0.0.1:8081/v1/chat/completions"
    assert request.headers["authorization"] == "Bearer session-key"
    body = json.loads(request.content)
    assert body["temperature"] == 0.2  # noqa: PLR2004
    assert body.get("max_completion_tokens", body.get("max_tokens")) == 64  # noqa: PLR2004


def test_structured_output_uses_a_json_schema_and_validates() -> None:
    bodies: list[dict[str, typing.Any]] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        bodies.append(json.loads(request.content))
        return httpx2.Response(200, json=_completion('{"word": "OK", "number": 3}'))

    controller = _through_controller(_provider(handler))

    result = asyncio.run(controller.chat("x", output_type=_Probe))

    assert result == _Probe(word="OK", number=3)
    response_format = bodies[0]["response_format"]
    assert response_format["type"] == "json_schema"
    assert "tools" not in bodies[0]
    assert set(response_format["json_schema"]["schema"]["required"]) == {
        "word",
        "number",
    }


def test_a_malformed_structured_answer_is_a_clean_error() -> None:
    def handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json=_completion('{"word": "NO"}'))

    with pytest.raises(AIStructuredOutputError) as error:
        asyncio.run(
            _through_controller(_provider(handler)).chat("x", output_type=_Probe),
        )

    assert "NO" not in str(error.value)


def test_a_server_error_is_reported_without_its_body() -> None:
    def handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(500, json={"error": {"message": PHI_REPLY}})

    with pytest.raises(LocalAIUnavailableError) as error:
        asyncio.run(_through_controller(_provider(handler)).chat(PHI_PROMPT))

    assert PHI_REPLY not in str(error.value)
    assert PHI_PROMPT not in str(error.value)


def test_a_timeout_is_a_local_ai_timeout() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ReadTimeout("slow", request=request)

    with pytest.raises(LocalAITimeoutError):
        asyncio.run(_through_controller(_provider(handler)).chat("x"))


def test_a_refused_connection_is_local_ai_unavailable() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("refused", request=request)

    with pytest.raises(LocalAIUnavailableError, match="not available"):
        asyncio.run(_through_controller(_provider(handler)).chat("x"))


def test_prompts_and_replies_are_never_logged(caplog: pytest.LogCaptureFixture) -> None:
    def handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json=_completion(PHI_REPLY))

    with caplog.at_level(logging.DEBUG, logger="engine"):
        asyncio.run(_through_controller(_provider(handler)).chat(PHI_PROMPT))

    assert "Local AI request completed" in caplog.text
    assert "Jane Example" not in caplog.text


@pytest.mark.parametrize(
    ("status_code", "expected", "error"),
    [
        (200, AIStatusValue.READY, None),
        (503, AIStatusValue.UNAVAILABLE, "still loading"),
    ],
)
def test_health_reads_the_servers_health_endpoint(
    status_code: int,
    expected: AIStatusValue,
    error: str | None,
) -> None:
    seen: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request.url.path)
        if request.url.path == "/v1/models":
            return httpx2.Response(200, json={"data": [{"id": "m"}]})
        return httpx2.Response(status_code, json={})

    status = asyncio.run(_provider(handler).health())

    assert seen[0] == "/health"
    assert status.status is expected
    assert (status.error is None) if error is None else error in (status.error or "")


@pytest.mark.parametrize(
    ("loaded", "shown"),
    [
        ("/Users/someone/models/Qwen3-14B-Q4_K_M.gguf", "Qwen3-14B-Q4_K_M"),
        ("C:\\Users\\someone\\models\\qwen.gguf", "qwen"),
        ("qwen3-14b", "qwen3-14b"),  # started with --alias
    ],
)
def test_ready_status_names_the_loaded_model_without_its_path(
    loaded: str,
    shown: str,
) -> None:
    headers: list[str | None] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path == "/v1/models":
            headers.append(request.headers.get("authorization"))
            return httpx2.Response(
                200,
                json={"object": "list", "data": [{"id": loaded}]},
            )
        return httpx2.Response(200, json={"status": "ok"})

    status = asyncio.run(_provider(handler, llama_api_key="k").health())

    assert status.model == shown
    assert "someone" not in status.model_dump_json()
    assert headers == ["Bearer k"]


def test_a_server_that_will_not_name_its_model_is_still_ready() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path == "/v1/models":
            return httpx2.Response(404)
        return httpx2.Response(200, json={"status": "ok"})

    status = asyncio.run(_provider(handler).health())

    assert status.status is AIStatusValue.READY
    assert status.model is None


def test_health_reports_a_server_that_is_not_running() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("refused", request=request)

    status = asyncio.run(_provider(handler).health())

    assert status.status is AIStatusValue.UNAVAILABLE
    assert status.error == "Local AI is not running."


def test_health_reports_a_disallowed_url_as_not_configured() -> None:
    status = asyncio.run(
        LocalAIProvider(_settings(llama_url="http://192.168.1.9:8080")).health(),
    )

    assert status.status is AIStatusValue.NOT_CONFIGURED


@pytest.mark.parametrize(
    "url",
    ["http://127.0.0.1:8080", "http://localhost:8080", "http://[::1]:8080"],
)
def test_local_urls_are_accepted(url: str) -> None:
    assert validate_local_url(url) == url


@pytest.mark.parametrize(
    "url",
    [
        "http://192.168.1.20:8080",
        "http://0.0.0.0:8080",
        "https://llama.example.com",
        "ftp://127.0.0.1/",
        "not a url",
    ],
)
def test_other_urls_are_refused(url: str) -> None:
    with pytest.raises(ProviderConfigurationError):
        validate_local_url(url)
    with pytest.raises(ProviderConfigurationError):
        LocalAIProvider(_settings(llama_url=url)).model()


def test_single_valued_properties_become_required() -> None:
    schema = {
        "type": "object",
        "properties": {
            "type": {"const": "weight", "default": "weight"},
            "unit": {"enum": ["lb"], "default": "lb"},
            "note": {"type": "string", "default": ""},
        },
        "required": [],
    }

    transformed = LocalJsonSchemaTransformer(schema).walk()

    assert transformed["required"] == ["type", "unit"]
