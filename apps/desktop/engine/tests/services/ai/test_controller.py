from __future__ import annotations

import asyncio
import typing

import pytest
from pydantic import BaseModel
from pydantic_ai.models.test import TestModel

from engine.models.ai import AIProvider, AIStatus, AIStatusValue
from engine.services.ai.controller import AIController
from engine.services.ai.errors import (
    AIStructuredOutputError,
    LocalAIUnavailableError,
    UnsupportedAIProviderError,
)

if typing.TYPE_CHECKING:
    from pydantic_ai.models import Model


class _Provider:
    """Records what the controller asked of it."""

    def __init__(self, kind: AIProvider, *, fails: bool = False) -> None:
        self.kind = kind
        self.fails = fails
        self.models = 0

    def model(self) -> Model:
        self.models += 1
        if self.fails:
            msg = "Local AI is not available."
            raise LocalAIUnavailableError(msg)
        return TestModel(custom_output_text="OK")

    async def health(self) -> AIStatus:
        return AIStatus(provider=self.kind, status=AIStatusValue.READY)


def _controller(
    selected: AIProvider | str,
    *,
    local_fails: bool = False,
) -> tuple[AIController, _Provider, _Provider]:
    local = _Provider(AIProvider.LOCAL, fails=local_fails)
    openai = _Provider(AIProvider.OPENAI)
    controller = AIController(
        local,
        openai,
        selected=lambda: typing.cast("AIProvider", selected),
    )
    return controller, local, openai


def test_local_is_used_when_selected() -> None:
    controller, local, openai = _controller(AIProvider.LOCAL)

    controller.model()

    assert (local.models, openai.models) == (1, 0)


def test_openai_is_used_when_selected() -> None:
    controller, local, openai = _controller(AIProvider.OPENAI)

    controller.model()

    assert (local.models, openai.models) == (0, 1)


def test_an_unsupported_provider_is_an_error() -> None:
    controller, _, _ = _controller("ollama")

    with pytest.raises(UnsupportedAIProviderError):
        controller.model()


def test_a_local_failure_never_falls_back_to_openai() -> None:
    controller, local, openai = _controller(AIProvider.LOCAL, local_fails=True)

    with pytest.raises(LocalAIUnavailableError):
        asyncio.run(controller.chat("anything"))

    assert local.models == 1
    assert openai.models == 0


def test_chat_returns_the_selected_providers_answer() -> None:
    controller, _, _ = _controller(AIProvider.LOCAL)

    assert asyncio.run(controller.chat("Respond with OK.")) == "OK"


def test_health_reports_the_selected_provider() -> None:
    controller, _, _ = _controller(AIProvider.OPENAI)

    status = asyncio.run(controller.health())

    assert status.provider is AIProvider.OPENAI


class _Strict(BaseModel):
    word: typing.Literal["OK"]


class _WrongShape(_Provider):
    def model(self) -> Model:
        return TestModel(custom_output_args={"word": "NO"})


def test_a_structure_that_never_validates_is_a_clean_error() -> None:
    controller = AIController(
        _WrongShape(AIProvider.LOCAL),
        _Provider(AIProvider.OPENAI),
        selected=lambda: AIProvider.LOCAL,
    )

    with pytest.raises(AIStructuredOutputError) as error:
        asyncio.run(controller.chat("x", output_type=_Strict))

    assert "NO" not in str(error.value)


def test_facts_are_recorded_with_the_model_that_answered() -> None:
    from engine.agents.data_extraction_agent import DataExtractionAgent  # noqa: PLC0415
    from engine.models.settings import LocalAISettings  # noqa: PLC0415
    from engine.services.ai.local_provider import LocalAIProvider  # noqa: PLC0415
    from engine.services.ai.openai_provider import (  # noqa: PLC0415
        CLOUD_MODEL,
        OpenAIProvider,
    )

    def agent_on(kind: AIProvider) -> DataExtractionAgent:
        return DataExtractionAgent(
            ai=AIController(
                LocalAIProvider(LocalAISettings(_env_file=None)),  # ty: ignore[unknown-argument]
                OpenAIProvider(token=lambda: "sk-test"),
                selected=lambda: kind,
            ),
        )

    assert agent_on(AIProvider.LOCAL).fact_model_name == "local"
    assert agent_on(AIProvider.OPENAI).unknown_document_model_name == (
        f"openai:{CLOUD_MODEL}"
    )
