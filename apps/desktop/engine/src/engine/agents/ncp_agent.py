"""On-device Nutrition Care Process note generation.

Runs where the clinical data already lives, so generating a note sends no
resident information anywhere by default. ``engine.services.ai_provider``
decides which model answers: on-device through Ollama unless the user has
switched on a hosted model in Settings and supplied their own API token.

One capability the server's agent had is missing: the diet and nutrition-care
manual lookups. Those tools search a pgvector knowledge base that exists only
server-side, so notes generated here rely on the prompt's own clinical rules
and the resident's record. See ``engine.agents.tools``.
"""

from __future__ import annotations

import asyncio
import typing

import logfire
from pydantic_ai import Agent

from engine.agents.prompts import ncp_instructions
from engine.agents.tools import (
    CALCULATOR_TOOLSET,
    KNOWLEDGE_SEARCH_TOOLSET,
    KnowledgeSearchToolDependencies,
)
from engine.services.ai_provider import build_model

if typing.TYPE_CHECKING:
    from engine.models.ncp_context import NCPGenerationRequest
    from engine.services.knowledge_service import KnowledgeService

logfire.instrument_pydantic_ai()

#: A local model is far slower than a hosted one, and a note that takes several
#: minutes is still useful -- but an unbounded wait is not, because the desktop
#: shell blocks on this call.
_GENERATION_TIMEOUT_SECONDS = 600


class NCPGenerationTimeoutError(TimeoutError):
    """Raised when the model exceeds the generation deadline."""


def build_ncp_agent() -> Agent[KnowledgeSearchToolDependencies, str]:
    """Build the note-generation agent.

    Built on demand rather than at import so the engine still imports with no
    model reachable at all.

    The calculator tools take no dependencies, so the agent's dependency type
    is the one the manual lookups need; the calculators simply ignore it.
    """
    agent = Agent(
        build_model(),
        output_type=str,
        deps_type=KnowledgeSearchToolDependencies,
        instructions=ncp_instructions(),
        toolsets=[CALCULATOR_TOOLSET, KNOWLEDGE_SEARCH_TOOLSET],
    )
    return typing.cast("Agent[KnowledgeSearchToolDependencies, str]", agent)


class NCPAgent:
    """Generate a Nutrition Care Process note on this device."""

    def __init__(
        self,
        agent: object | None = None,
        knowledge_service: KnowledgeService | None = None,
    ) -> None:
        """Store an injected agent, building the real one only when used.

        ``knowledge_service`` is what the manual-lookup tools run against. It
        is optional: a note can still be written without it, from the prompt's
        own clinical rules and the resident's supplied facts. A lookup
        attempted without one fails that tool call rather than the run.
        """
        self._agent = agent
        self._knowledge_service = knowledge_service

    async def run(self, request: NCPGenerationRequest) -> str:
        """Generate one note from a prepared generation request."""
        agent = self._agent or build_ncp_agent()
        try:
            async with asyncio.timeout(_GENERATION_TIMEOUT_SECONDS):
                result = await agent.run(  # ty: ignore[unresolved-attribute]
                    request.model_dump_json(exclude_none=True),
                    deps=KnowledgeSearchToolDependencies(
                        knowledge_service=self._knowledge_service,
                    ),
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


__all__ = ["NCPAgent", "NCPGenerationTimeoutError", "build_ncp_agent"]
