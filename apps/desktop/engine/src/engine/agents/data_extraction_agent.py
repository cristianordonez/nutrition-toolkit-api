"""AI extraction of nutrition facts from document text.

Runs on OpenAI by default. Setting ``use_local_extraction`` moves inference
on-device through Ollama instead; the prompt, agent wiring, and output schema
are identical either way, only the model changes.

Local extraction stays opt-in because this schema is demanding -- a twelve-way
discriminated union across ~23 nested definitions -- and a model that cannot
hold it returns confidently wrong facts rather than failing. Measure a local
model against the hosted one on real documents before trusting it.
"""

from __future__ import annotations

import functools
import pathlib
import typing
from datetime import date, datetime  # noqa: TC003

import logfire
from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIResponsesModel
from pydantic_ai.providers.ollama import OllamaProvider
from pydantic_ai.providers.openai import OpenAIProvider

from engine.models.ai_extraction import (  # noqa: TC001
    AIExtractedFact,
    AIUnknownDocumentFact,
)
from engine.models.settings import SETTINGS
from engine.services.local_model import resolve_model

if typing.TYPE_CHECKING:
    from pydantic_ai.models import Model

logfire.instrument_pydantic_ai()

DATA_EXTRACTION_MODEL = "gpt-5.6-luna"

_PROMPT_PATH = pathlib.Path(__file__).parent / "prompts" / "data_extraction_prompt.md"
_instructions = _PROMPT_PATH.read_text(encoding="utf-8")


#: Where inference runs. "openai" is hosted, "ollama" is on-device.
ExtractionProvider = typing.Literal["openai", "ollama"]


def configured_provider() -> ExtractionProvider:
    """Return the provider the settings select."""
    return "ollama" if SETTINGS.use_local_extraction else "openai"


def build_model(provider: ExtractionProvider | None = None) -> Model:
    """Build an extraction model, defaulting to the configured provider.

    Deferred rather than built at import so neither provider's prerequisites
    are needed just to import the engine: running on-device needs no OpenAI
    key, and running hosted needs no Ollama daemon. Taking the provider as an
    argument also lets one process build both, which is what comparing them
    requires.
    """
    if (provider or configured_provider()) == "ollama":
        model_name = resolve_model(override=SETTINGS.ollama_model)
        # Ollama serves the OpenAI-compatible API under /v1, and the provider
        # does not append it.
        base_url = f"{SETTINGS.ollama_host.rstrip('/')}/v1"
        return OpenAIChatModel(model_name, provider=OllamaProvider(base_url=base_url))
    return OpenAIResponsesModel(
        DATA_EXTRACTION_MODEL,
        provider=OpenAIProvider(api_key=SETTINGS.open_ai_api_key),
    )


class ExtractionInput(BaseModel):
    """Input for the data extraction agent."""

    text: str
    document_filename: str | None = None
    note_date: datetime | None = None
    known_person_name: str | None = None
    known_date_of_birth: date | None = None


class ExtractedClinicalFacts(BaseModel):
    """Clinical facts not handled by a dedicated document extractor."""

    facts: list[AIExtractedFact] = Field(default_factory=list)


class UnknownDocumentExtractionResult(BaseModel):
    """Facts and identity clues extracted from an unknown document."""

    facts: list[AIUnknownDocumentFact] = Field(default_factory=list)


def build_unknown_document_agent(
    provider: ExtractionProvider | None = None,
) -> Agent[None, UnknownDocumentExtractionResult]:
    """Build an unknown-document agent bound to one provider."""
    agent = Agent(
        build_model(provider),
        output_type=UnknownDocumentExtractionResult,
        instructions=_instructions,
    )
    return typing.cast("Agent[None, UnknownDocumentExtractionResult]", agent)


@functools.cache
def _fact_extraction_agent() -> Agent[None, ExtractedClinicalFacts]:
    """Return the shared narrative-fact extraction agent."""
    agent = Agent(
        build_model(),
        output_type=ExtractedClinicalFacts,
        instructions=_instructions,
    )
    return typing.cast("Agent[None, ExtractedClinicalFacts]", agent)


@functools.cache
def _unknown_document_agent() -> Agent[None, UnknownDocumentExtractionResult]:
    """Return the shared unknown-document extraction agent."""
    return build_unknown_document_agent()


class DataExtractionAgent:
    """Extract nutrition facts from text."""

    def __init__(
        self,
        fact_agent: Agent[None, ExtractedClinicalFacts] | None = None,
        unknown_document_agent: Agent[None, UnknownDocumentExtractionResult]
        | None = None,
    ) -> None:
        """Store injected agents, building real ones only when first used."""
        self._fact_agent = fact_agent
        self._unknown_document_agent = unknown_document_agent

    @property
    def fact_agent(self) -> Agent[None, ExtractedClinicalFacts]:
        """The narrative-fact agent, built on first use."""
        return self._fact_agent or _fact_extraction_agent()

    @property
    def unknown_document_agent(
        self,
    ) -> Agent[None, UnknownDocumentExtractionResult]:
        """The unknown-document agent, built on first use."""
        return self._unknown_document_agent or _unknown_document_agent()

    async def run(
        self,
        extraction_input: ExtractionInput,
    ) -> ExtractedClinicalFacts:
        """Extract nutrition facts from text associated with one source."""
        if not extraction_input.text.strip():
            return ExtractedClinicalFacts()
        results = await self.fact_agent.run(extraction_input.model_dump_json())
        return results.output

    async def run_unknown_document(
        self,
        extraction_input: ExtractionInput,
    ) -> list[AIUnknownDocumentFact]:
        """Extract facts and person identity clues from an unknown document."""
        if not extraction_input.text.strip():
            return []
        result = await self.unknown_document_agent.run(
            extraction_input.model_dump_json(),
        )
        return result.output.facts


__all__ = [
    "DataExtractionAgent",
    "ExtractedClinicalFacts",
]
