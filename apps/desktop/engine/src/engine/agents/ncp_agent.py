"""On-device Nutrition Care Process generation.

Generates the note in this process instead of posting to cloud-api, so the
desktop app needs no server, database, or API key to produce a note. The
prompt is the one in ``ntk-core``, shared with cloud-api so the two cannot
drift.

One capability is missing compared with cloud-api: the diet and
nutrition-care manual lookups. Those tools search a pgvector knowledge base
that only exists cloud-side, so notes generated here rely on the prompt's own
clinical rules and the resident's data. Calculation tools, which need no
services, are registered exactly as they are cloud-side.
"""

from __future__ import annotations

import asyncio
import typing

import logfire
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider

from engine.models.settings import SETTINGS
from ntk.agents import (
    CALCULATOR_TOOLSET,
    CalculatorToolDependencies,
    ncp_instructions,
)

if typing.TYPE_CHECKING:
    from ntk.models.ncp_context import NCPGenerationRequest

logfire.instrument_pydantic_ai()

NCP_MODEL = "gpt-5.6-terra"

_GENERATION_TIMEOUT_SECONDS = 180


class NCPGenerationTimeoutError(TimeoutError):
    """Raised when the model exceeds the generation deadline."""


def build_ncp_agent() -> Agent[CalculatorToolDependencies, str]:
    """Build the on-device note-generation agent.

    Built on demand rather than at import so the engine still imports without
    an OpenAI key.
    """
    model = OpenAIResponsesModel(
        NCP_MODEL,
        provider=OpenAIProvider(api_key=SETTINGS.open_ai_api_key),
    )
    agent = Agent(
        model,
        output_type=str,
        deps_type=CalculatorToolDependencies,
        instructions=ncp_instructions(),
        toolsets=[CALCULATOR_TOOLSET],
    )
    return typing.cast("Agent[CalculatorToolDependencies, str]", agent)


class LocalNCPAgent:
    """Generate a Nutrition Care Process note without leaving the device."""

    def __init__(self, agent: object | None = None) -> None:
        """Store an injected agent, building the real one only when used."""
        self._agent = agent

    async def run(self, request: NCPGenerationRequest) -> str:
        """Generate one note from a prepared generation request."""
        agent = self._agent or build_ncp_agent()
        try:
            async with asyncio.timeout(_GENERATION_TIMEOUT_SECONDS):
                result = await agent.run(  # ty: ignore[unresolved-attribute]
                    request.model_dump_json(exclude_none=True),
                    deps=CalculatorToolDependencies(),
                )
        except TimeoutError as error:
            message = (
                f"Note generation timed out after {_GENERATION_TIMEOUT_SECONDS} seconds"
            )
            raise NCPGenerationTimeoutError(message) from error
        note = str(result.output).strip()
        if not note:
            message = "The model returned an empty note"
            raise RuntimeError(message)
        return note


__all__ = [
    "NCP_MODEL",
    "LocalNCPAgent",
    "NCPGenerationTimeoutError",
    "build_ncp_agent",
]
