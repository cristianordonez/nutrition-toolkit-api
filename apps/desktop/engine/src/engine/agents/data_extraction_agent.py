"""AI extraction of nutrition facts from document text.

Runs on-device by default -- on the local llama.cpp server -- so a resident's
documents are not sent anywhere. The model comes from
``engine.services.ai.controller.AIController``, which selects the provider for
every agent alike; the prompt, agent wiring, and output schema are identical
on every provider, and nothing here knows which one answered.

Worth measuring before trusting: this schema is demanding -- a twelve-way
discriminated union across ~23 nested definitions -- and a model that cannot
hold it returns confidently wrong facts rather than failing. Compare a local
model against a hosted one on real documents with ``engine eval extraction``.
"""

from __future__ import annotations

import functools
import pathlib
import typing
from datetime import date, datetime  # noqa: TC003

import logfire
from pydantic import BaseModel, Field
from pydantic_ai import Agent

from engine.models.ai_extraction import (  # noqa: TC001
    AIExtractedFact,
    AIUnknownDocumentFact,
)
from engine.services.ai.boundary import recorded_name_of
from engine.services.ai.controller import AIController, ai_controller

if typing.TYPE_CHECKING:
    from pydantic_ai.models import Model

    from engine.models.ai import AIProvider

# Traces keep timings and model names only. Prompts and completions hold
# clinical data and must never be exported, whichever provider runs them.
logfire.instrument_pydantic_ai(include_content=False, include_binary_content=False)

_PROMPT_PATH = pathlib.Path(__file__).parent / "prompts" / "data_extraction_prompt.md"
_instructions = _PROMPT_PATH.read_text(encoding="utf-8")

#: How many times to send a schema violation back to the model. The default of
#: one is too few here: the extraction result is a list of facts, so a single
#: omitted field on the fifth fact fails the whole response, and losing that
#: response means losing a 600-token window of a clinical document outright.
#: The retry carries the validation error, naming the field that was missed, so
#: it usually succeeds -- and the chunk is skipped only when it does not.
_MODEL_RETRIES = 3


def build_model(
    provider: AIProvider | None = None,
    *,
    ai: AIController | None = None,
) -> Model:
    """Return an extraction model from the AI controller.

    The controller picks the provider, so extraction and note generation can
    never disagree about where clinical data is sent. ``provider`` overrides
    the selection only for side-by-side comparisons.
    """
    return (ai or ai_controller()).model(provider=provider)


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
    provider: AIProvider | None = None,
    *,
    ai: AIController | None = None,
) -> Agent[None, UnknownDocumentExtractionResult]:
    """Build an unknown-document agent on the controller's model."""
    agent = Agent(
        build_model(provider, ai=ai),
        output_type=UnknownDocumentExtractionResult,
        instructions=_instructions,
        retries=_MODEL_RETRIES,
    )
    return typing.cast("Agent[None, UnknownDocumentExtractionResult]", agent)


def _build_fact_agent(ai: AIController) -> Agent[None, ExtractedClinicalFacts]:
    agent = Agent(
        build_model(ai=ai),
        output_type=ExtractedClinicalFacts,
        instructions=_instructions,
        retries=_MODEL_RETRIES,
    )
    return typing.cast("Agent[None, ExtractedClinicalFacts]", agent)


@functools.cache
def _fact_extraction_agent() -> Agent[None, ExtractedClinicalFacts]:
    """Return the shared narrative-fact extraction agent."""
    return _build_fact_agent(ai_controller())


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
        *,
        ai: AIController | None = None,
    ) -> None:
        """Store injected agents, building real ones only when first used.

        ``ai`` supplies the models; the process's controller when omitted.
        """
        self._fact_agent = fact_agent
        self._unknown_document_agent = unknown_document_agent
        self._ai = ai

    @property
    def fact_agent(self) -> Agent[None, ExtractedClinicalFacts]:
        """The narrative-fact agent, built on first use."""
        if self._fact_agent is None:
            self._fact_agent = (
                _fact_extraction_agent()
                if self._ai is None
                else _build_fact_agent(self._ai)
            )
        return self._fact_agent

    @property
    def fact_model_name(self) -> str | None:
        """The model narrative facts are recorded as extracted by."""
        return recorded_name_of(self.fact_agent.model)

    @property
    def unknown_document_model_name(self) -> str | None:
        """The model unknown-document facts are recorded as extracted by."""
        return recorded_name_of(self.unknown_document_agent.model)

    @property
    def unknown_document_agent(
        self,
    ) -> Agent[None, UnknownDocumentExtractionResult]:
        """The unknown-document agent, built on first use."""
        if self._unknown_document_agent is None:
            self._unknown_document_agent = (
                _unknown_document_agent()
                if self._ai is None
                else build_unknown_document_agent(ai=self._ai)
            )
        return self._unknown_document_agent

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
