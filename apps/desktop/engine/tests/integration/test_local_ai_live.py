"""Opt-in check against a real llama-server.

Skipped unless ``NUTRITION_AI_LLAMA_URL`` names a running server, so the
normal suite never needs a model. Start one first, e.g.::

    llama-server -m /path/model.gguf --host 127.0.0.1 --port 8080

The prompts are fixed, non-clinical probes, sent through ``AIController``
exactly as the agents' requests are.
"""

from __future__ import annotations

import asyncio
import os
import typing

import pytest
from pydantic import BaseModel

from engine.models.ai import AIProvider, AIStatusValue
from engine.models.settings import LocalAISettings
from engine.services.ai.controller import AIController
from engine.services.ai.local_provider import LocalAIProvider
from engine.services.ai.openai_provider import OpenAIProvider

pytestmark = pytest.mark.skipif(
    not os.environ.get("NUTRITION_AI_LLAMA_URL"),
    reason="set NUTRITION_AI_LLAMA_URL to a running llama-server",
)


class _Probe(BaseModel):
    word: typing.Literal["OK"]
    number: int


def test_local_ai_answers_through_the_controller() -> None:
    controller = AIController(
        LocalAIProvider(LocalAISettings()),
        # Present only to prove it is never used while LOCAL is selected.
        OpenAIProvider(token=lambda: None),
        selected=lambda: AIProvider.LOCAL,
    )

    async def run() -> tuple[AIStatusValue, str, _Probe]:
        health = await controller.health()
        reply = await controller.chat("Respond with the word OK.")
        probe = await controller.chat(
            "Return the word OK and the number 3.",
            output_type=_Probe,
        )
        return health.status, str(reply), probe

    status, reply, probe = asyncio.run(run())

    assert status is AIStatusValue.READY
    assert "ok" in reply.casefold()
    assert probe == _Probe(word="OK", number=3)
