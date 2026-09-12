from __future__ import annotations

import typing

from ntk.services.nutrition_data import fatsecret_service
from ntk.services.nutrition_data.fatsecret_service import FatSecretClient

if typing.TYPE_CHECKING:
    import pytest


class Response:
    def __init__(self, payload: dict[str, object], status_code: int = 200) -> None:
        self.payload = payload
        self.status_code = status_code
        self.raised = False

    def raise_for_status(self) -> None:
        self.raised = True

    def json(self) -> dict[str, object]:
        return self.payload


def test_fatsecret_authenticates_and_retries_an_expired_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token_responses = iter(
        [Response({"access_token": "first"}), Response({"access_token": "second"})],
    )
    search_responses = iter(
        [Response({}, status_code=401), Response({"foods": ["shake"]})],
    )
    post_calls: list[dict[str, object]] = []
    get_calls: list[dict[str, object]] = []

    def post(url: str, **kwargs: object) -> Response:
        post_calls.append({"url": url, **kwargs})
        return next(token_responses)

    def get(url: str, **kwargs: object) -> Response:
        get_calls.append({"url": url, **kwargs})
        return next(search_responses)

    monkeypatch.setattr(fatsecret_service.requests, "post", post)
    monkeypatch.setattr(fatsecret_service.requests, "get", get)

    client = FatSecretClient()
    result = client.search_foods("nutrition shake")

    assert result == {"foods": ["shake"]}
    assert client.access_token == "second"  # noqa: S105
    assert len(post_calls) == 2  # noqa: PLR2004
    assert post_calls[0]["data"] == {
        "grant_type": "client_credentials",
        "scope": "basic",
    }
    assert get_calls[0]["params"] == {
        "search_expression": "nutrition shake",
        "format": "json",
        "max_results": 20,
    }
    assert get_calls[1]["headers"] == {"Authorization": "Bearer second"}


def test_fatsecret_reauthenticates_when_token_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        fatsecret_service.requests,
        "post",
        lambda *_args, **_kwargs: Response({"access_token": "token"}),
    )
    monkeypatch.setattr(
        fatsecret_service.requests,
        "get",
        lambda *_args, **_kwargs: Response({"foods": []}),
    )
    client = FatSecretClient()
    client.access_token = None

    assert client.search_foods("missing") == {"foods": []}
    assert client.access_token == "token"  # noqa: S105
