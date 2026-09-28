"""The extraction agents can actually be built, on either provider.

Every other test in this suite injects a stub agent, which is right -- they
are testing extraction logic, not pydantic-ai. The cost is that nothing
exercised the real `Agent(...)` call, so a keyword argument that pydantic-ai
does not accept passed the whole suite and only failed at run time, once per
chunk, after the document had already been read. These build the real thing.
"""

from __future__ import annotations

import pytest

from engine.agents import data_extraction_agent
from engine.agents.data_extraction_agent import (
    DataExtractionAgent,
    UnknownDocumentExtractionResult,
    build_unknown_document_agent,
)
from engine.models.ai import AIProvider
from engine.models.settings import LocalAISettings
from engine.services.ai.controller import AIController
from engine.services.ai.local_provider import LocalAIProvider
from engine.services.ai.openai_provider import OpenAIProvider


def _controller(selected: AIProvider) -> AIController:
    """Both real providers; building a model contacts neither."""
    return AIController(
        LocalAIProvider(LocalAISettings(_env_file=None)),  # ty: ignore[unknown-argument]
        OpenAIProvider(token=lambda: "test-token-not-used"),
        selected=lambda: selected,
    )


@pytest.mark.parametrize("provider", list(AIProvider))
def test_the_unknown_document_agent_builds(provider: AIProvider) -> None:
    agent = build_unknown_document_agent(ai=_controller(provider))

    assert agent.output_type is UnknownDocumentExtractionResult


@pytest.mark.parametrize("provider", list(AIProvider))
def test_the_narrative_fact_agent_builds(provider: AIProvider) -> None:
    assert DataExtractionAgent(ai=_controller(provider)).fact_agent is not None


def test_the_default_agent_builds_without_a_running_server() -> None:
    data_extraction_agent._fact_extraction_agent.cache_clear()  # noqa: SLF001

    assert data_extraction_agent._fact_extraction_agent() is not None  # noqa: SLF001


@pytest.mark.parametrize("provider", list(AIProvider))
def test_a_schema_violation_is_sent_back_to_the_model(provider: AIProvider) -> None:
    """One omitted field must not cost a whole window of a document."""
    agent = build_unknown_document_agent(ai=_controller(provider))

    assert agent._max_output_retries > 1  # noqa: SLF001
