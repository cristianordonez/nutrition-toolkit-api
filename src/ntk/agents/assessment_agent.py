"""Agent for generating nutrition assessments."""

from __future__ import annotations

import asyncio
import json
import pathlib
import typing

import logfire
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider

from ntk.models.settings import SETTINGS
from ntk.services.embedding_service import EmbeddingService
from ntk.utils.tokens import truncate_to_tokens

if typing.TYPE_CHECKING:
    from ntk.models.rag import RagSearchMatch


class ResidentContext(typing.Protocol):
    """Data contract required by the assessment agent."""

    def summary(self, context: str | None = None) -> str:
        """Return resident data suitable for semantic retrieval."""
        ...

    def llm_payload(self) -> dict[str, object]:
        """Return structured resident data for the assessment prompt."""
        ...


logfire.instrument_pydantic_ai()

ASSESSMENT_MODEL = "gpt-5.6-sol"

_CONTEXT_TOKENS = 1_000
_QUERY_TOKENS = 2_000
_KNOWLEDGE_MATCH_LIMIT = 3
_ASSESSMENT_MATCH_LIMIT = 5
_KNOWLEDGE_CHUNK_TOKENS = 800
_ASSESSMENT_CHUNK_TOKENS = 1_200
_ASSESSMENT_GENERATION_TIMEOUT_SECONDS = 180
_PROMPT_PATH = pathlib.Path(__file__).parent / "prompts" / "assessment_prompt.md"
_provider = OpenAIProvider(api_key=SETTINGS.open_ai_api_key)
_model = OpenAIResponsesModel(ASSESSMENT_MODEL, provider=_provider)
assessment_agent = Agent(
    _model,
    output_type=str,
    instructions=_PROMPT_PATH.read_text(encoding="utf-8"),
)


class AssessmentGenerationTimeoutError(TimeoutError):
    """Raised when the assessment model exceeds the request deadline."""


class AssessmentAgent:
    """Create a nutrition assessment from resident and retrieved context."""

    def __init__(
        self,
        agent: Agent[None, str] | None = None,
        embedding_service: EmbeddingService | None = None,
    ) -> None:
        """Initialize the assessment agent or use an injected test double."""
        self.agent = agent or assessment_agent
        self.embedding_service = embedding_service or EmbeddingService()

    async def run(
        self,
        resident_context: ResidentContext,
        context: str | None = None,
    ) -> str:
        """Generate a note from the three explicitly defined input sources."""
        try:
            async with asyncio.timeout(_ASSESSMENT_GENERATION_TIMEOUT_SECONDS):
                bounded_context = (
                    truncate_to_tokens(context.strip(), _CONTEXT_TOKENS)
                    if context and context.strip()
                    else None
                )
                query = truncate_to_tokens(
                    resident_context.summary(context=bounded_context),
                    _QUERY_TOKENS,
                )
                knowledge_output, assessment_output = await asyncio.to_thread(
                    self.embedding_service.search_context,
                    query,
                    knowledge_top_k=_KNOWLEDGE_MATCH_LIMIT,
                    assessment_top_k=_ASSESSMENT_MATCH_LIMIT,
                )
                payload = {
                    "resident_context": resident_context.llm_payload(),
                    "retrieved_knowledge": [
                        self._match_payload(match, _KNOWLEDGE_CHUNK_TOKENS)
                        for match in knowledge_output
                    ],
                    "previous_assessments": [
                        self._match_payload(match, _ASSESSMENT_CHUNK_TOKENS)
                        for match in assessment_output
                    ],
                    "optional_context": bounded_context,
                }
                result = await self.agent.run(json.dumps(payload, default=str))
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

    @staticmethod
    def _match_payload(match: RagSearchMatch, max_tokens: int) -> dict[str, object]:
        """Return only the bounded RAG fields needed by the assessment model."""
        return {
            "filename": match.filename,
            "chunk_text": truncate_to_tokens(match.chunk_text, max_tokens),
            "similarity": match.similarity,
        }
