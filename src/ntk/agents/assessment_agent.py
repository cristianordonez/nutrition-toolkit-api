"""Agent for generating nutrition assessments."""

from __future__ import annotations

import asyncio
import pathlib
import typing

import logfire
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider

from ntk.agents.tools import (
    CALCULATOR_TOOLSET,
    KNOWLEDGE_SEARCH_TOOLSET,
    AssessmentToolDependencies,
)
from ntk.models.settings import SETTINGS

if typing.TYPE_CHECKING:
    from ntk.models import BudgetedAssessmentContext
    from ntk.repositories.food_repo import FoodRepo
    from ntk.services.embedding_service import EmbeddingService


logfire.instrument_pydantic_ai()

ASSESSMENT_MODEL = "gpt-5.6-terra"

_ASSESSMENT_GENERATION_TIMEOUT_SECONDS = 180
_PROMPT_PATH = pathlib.Path(__file__).parent / "prompts" / "assessment_prompt.md"
_provider = OpenAIProvider(api_key=SETTINGS.open_ai_api_key)
_model = OpenAIResponsesModel(ASSESSMENT_MODEL, provider=_provider)
assessment_agent = Agent(
    _model,
    output_type=str,
    deps_type=AssessmentToolDependencies,
    instructions=_PROMPT_PATH.read_text(encoding="utf-8"),
    toolsets=[CALCULATOR_TOOLSET, KNOWLEDGE_SEARCH_TOOLSET],
)


class AssessmentGenerationTimeoutError(TimeoutError):
    """Raised when the assessment model exceeds the request deadline."""


class AssessmentAgent:
    """Create a nutrition assessment from fully prepared context and tools."""

    def __init__(
        self,
        agent: Agent[AssessmentToolDependencies, str] | None = None,
        food_repo: FoodRepo | None = None,
        embedding_service: EmbeddingService | None = None,
    ) -> None:
        """Initialize the assessment agent or use an injected test double."""
        self.agent = agent or assessment_agent
        self.food_repo = food_repo
        self.embedding_service = embedding_service

    async def run(
        self,
        budgeted_assessment_context: BudgetedAssessmentContext,
    ) -> str:
        """Generate a note from a fully prepared assessment context."""
        try:
            async with asyncio.timeout(_ASSESSMENT_GENERATION_TIMEOUT_SECONDS):
                if self.food_repo is None:
                    message = "A food repository is required for assessment tools"
                    raise RuntimeError(message)
                if self.embedding_service is None:
                    message = "An embedding service is required for assessment tools"
                    raise RuntimeError(message)
                result = await self.agent.run(
                    budgeted_assessment_context.model_dump_json(exclude_none=True),
                    deps=AssessmentToolDependencies(
                        food_repo=self.food_repo,
                        embedding_service=self.embedding_service,
                    ),
                )
        except TimeoutError as error:
            message = (
                "Assessment generation timed out after "
                f"{_ASSESSMENT_GENERATION_TIMEOUT_SECONDS} seconds"
            )
            raise AssessmentGenerationTimeoutError(message) from error
        note = result.output.strip()
        if not note:
            msg = "Assessment agent returned an empty note"
            raise RuntimeError(msg)
        return note
