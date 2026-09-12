"""AI extraction of nutrition facts from document text."""

from __future__ import annotations

import pathlib
from datetime import datetime  # noqa: TC003

import logfire
from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider

from ntk.models.ai_extraction import (  # noqa: TC001
    AIExtractedClinicalFact,
    AIUnknownDocumentFact,
)
from ntk.models.settings import SETTINGS

logfire.instrument_pydantic_ai()

DATA_EXTRACTION_MODEL = "gpt-5.6-luna"

_PROMPT_PATH = pathlib.Path(__file__).parent / "prompts" / "data_extraction_prompt.md"
_instructions = _PROMPT_PATH.read_text(encoding="utf-8")
_provider = OpenAIProvider(api_key=SETTINGS.open_ai_api_key)
_model = OpenAIResponsesModel(DATA_EXTRACTION_MODEL, provider=_provider)


class ExtractionInput(BaseModel):
    """Input for the data extraction agent."""

    text: str
    document_filename: str | None = None
    note_date: datetime | None = None


class ExtractedClinicalFacts(BaseModel):
    """Clinical facts not handled by a dedicated document extractor."""

    facts: list[AIExtractedClinicalFact] = Field(default_factory=list)


class UnknownDocumentExtractionResult(BaseModel):
    """Facts and identity clues extracted from an unknown document."""

    facts: list[AIUnknownDocumentFact] = Field(default_factory=list)


_fact_extraction_agent = Agent(
    _model,
    output_type=ExtractedClinicalFacts,
    instructions=_instructions,
)

_unknown_document_agent = Agent(
    _model,
    output_type=UnknownDocumentExtractionResult,
    instructions=_instructions,
)


class DataExtractionAgent:
    """Extract nutrition facts from text."""

    def __init__(
        self,
        fact_agent: Agent[None, ExtractedClinicalFacts] | None = None,
        unknown_document_agent: Agent[None, UnknownDocumentExtractionResult]
        | None = None,
    ) -> None:
        """Initialize the underlying extraction agent."""
        self.fact_agent = fact_agent or _fact_extraction_agent
        self.unknown_document_agent = unknown_document_agent or _unknown_document_agent

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
