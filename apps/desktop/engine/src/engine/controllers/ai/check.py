"""Prove the selected AI provider works with a tiny, non-clinical request.

Goes through ``AIController`` exactly as the agents do. The prompts are fixed
probes; no clinical data is involved. For Local AI, llama-server must already
be running at ``NUTRITION_AI_LLAMA_URL``.
"""

from __future__ import annotations

import time
import typing

from pydantic import BaseModel, Field

from engine.controllers.base import BaseController
from engine.models.ai import AIProvider  # noqa: TC001 - Pydantic field type
from engine.models.base import ConsoleRenderableModel
from engine.models.output import Output
from engine.services.ai.controller import AIController, ai_controller

PROBE_PROMPT = "Respond with the word OK."
STRUCTURED_PROMPT = "Return the word OK and the number 3."


class StructuredProbe(BaseModel):
    """A small schema to prove constrained structured output."""

    word: typing.Literal["OK"]
    number: int


class AICheckOptions(BaseModel):
    """What to check."""

    structured: bool = Field(
        default=False,
        description="Also check schema-constrained structured output",
    )


class AICheckResult(ConsoleRenderableModel):
    """What the probe saw."""

    provider: AIProvider
    reply: str
    reply_ok: bool
    seconds: float
    structured: StructuredProbe | None = None

    def to_console(self) -> str:
        """Render the outcome as formatted JSON."""
        return self.model_dump_json(indent=2)


class AICheckController(BaseController):
    """Send a probe through the AI controller and report the answer."""

    name = "check"
    help = "Check the selected AI provider with a tiny non-clinical request"
    options_model = AICheckOptions

    def __init__(self, ai: AIController | None = None) -> None:
        """Store the controller to check, if injected."""
        self.ai = ai

    async def run(self, options: AICheckOptions) -> Output[AICheckResult]:
        """Run the probe on the selected provider."""
        ai = self.ai or ai_controller()
        provider = ai.provider().kind
        started = time.monotonic()
        reply = str(await ai.chat(PROBE_PROMPT)).strip()
        seconds = time.monotonic() - started
        structured = (
            await ai.chat(STRUCTURED_PROMPT, output_type=StructuredProbe)
            if options.structured
            else None
        )
        return Output(
            result=AICheckResult(
                provider=provider,
                reply=reply,
                reply_ok="ok" in reply.casefold(),
                seconds=round(seconds, 2),
                structured=structured,
            ),
            controller=self.name,
            exit_code=0,
        )


__all__ = ["AICheckController", "AICheckOptions", "AICheckResult", "StructuredProbe"]
