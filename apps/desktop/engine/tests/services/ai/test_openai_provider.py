from __future__ import annotations

import asyncio

import pytest

from engine.models.ai import AIProvider, AIStatusValue
from engine.services.ai.errors import OpenAIConfigurationError
from engine.services.ai.openai_provider import CLOUD_MODEL, OpenAIProvider


def test_without_a_token_openai_refuses_rather_than_switching() -> None:
    with pytest.raises(OpenAIConfigurationError, match="no API token"):
        OpenAIProvider(token=lambda: None).model()


def test_with_a_token_it_builds_the_hosted_model() -> None:
    provider = OpenAIProvider(token=lambda: "sk-test")

    assert provider.model().model_name == CLOUD_MODEL


@pytest.mark.parametrize(
    ("token", "expected"),
    [("sk-test", AIStatusValue.READY), (None, AIStatusValue.NOT_CONFIGURED)],
)
def test_health_reflects_the_stored_token(
    token: str | None,
    expected: AIStatusValue,
) -> None:
    status = asyncio.run(OpenAIProvider(token=lambda: token).health())

    assert status.provider is AIProvider.OPENAI
    assert status.status is expected


def test_ready_status_names_the_hosted_model() -> None:
    status = asyncio.run(OpenAIProvider(token=lambda: "sk-test").health())

    assert status.model == CLOUD_MODEL
