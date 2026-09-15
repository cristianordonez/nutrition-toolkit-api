"""Agent for generating Nutrition Care Process notes."""

from __future__ import annotations

import asyncio
import pathlib
import typing

import logfire
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider

from api.agents.tools import (
    CALCULATOR_TOOLSET,
    KNOWLEDGE_SEARCH_TOOLSET,
    NCPToolDependencies,
)
from api.models.settings import SETTINGS

if typing.TYPE_CHECKING:
    from api.models.ncp_context import BudgetedNCPContext
    from api.services.embedding_service import EmbeddingService


logfire.instrument_pydantic_ai()

NCP_MODEL = "gpt-5.6-terra"

_NCP_GENERATION_TIMEOUT_SECONDS = 180
_PROMPT_PATH = pathlib.Path(__file__).parent / "prompts" / "ncp_prompt.md"
_provider = OpenAIProvider(api_key=SETTINGS.open_ai_api_key)
_model = OpenAIResponsesModel(NCP_MODEL, provider=_provider)
ncp_agent = Agent(
    _model,
    output_type=str,
    deps_type=NCPToolDependencies,
    instructions=_PROMPT_PATH.read_text(encoding="utf-8"),
    toolsets=[CALCULATOR_TOOLSET, KNOWLEDGE_SEARCH_TOOLSET],
)


class NCPGenerationTimeoutError(TimeoutError):
    """Raised when the NCP model exceeds the request deadline."""


class NutritionCareProcessAgent:
    """Create a Nutrition Care Process note from prepared context and tools."""

    def __init__(
        self,
        agent: Agent[NCPToolDependencies, str] | None = None,
        embedding_service: EmbeddingService | None = None,
    ) -> None:
        """Initialize the NCP agent or use an injected test double."""
        self.agent = agent or ncp_agent
        self.embedding_service = embedding_service

    async def run(
        self,
        budgeted_ncp_context: BudgetedNCPContext,
    ) -> str:
        """Generate a note from a fully prepared NCP context."""
        try:
            async with asyncio.timeout(_NCP_GENERATION_TIMEOUT_SECONDS):
                if self.embedding_service is None:
                    message = "An embedding service is required for ncp tools"
                    raise RuntimeError(message)
                result = await self.agent.run(
                    budgeted_ncp_context.model_dump_json(exclude_none=True),
                    deps=NCPToolDependencies(
                        embedding_service=self.embedding_service,
                    ),
                )
        except TimeoutError as error:
            message = (
                "Nutrition Care Process generation timed out after "
                f"{_NCP_GENERATION_TIMEOUT_SECONDS} seconds"
            )
            raise NCPGenerationTimeoutError(message) from error
        note = result.output.strip()
        if not note:
            msg = "Nutrition Care Process agent returned an empty note"
            raise RuntimeError(msg)
        return note
