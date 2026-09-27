"""The extraction agents can actually be built.

Every other test in this suite injects a stub agent, which is right -- they
are testing extraction logic, not pydantic-ai. The cost is that nothing
exercised the real `Agent(...)` call, so a keyword argument that pydantic-ai
does not accept passed the whole suite and only failed at run time, once per
chunk, after the document had already been read. These build the real thing.
"""

from __future__ import annotations

import typing

import pytest

from engine.agents import data_extraction_agent
from engine.agents.data_extraction_agent import (
    UnknownDocumentExtractionResult,
    build_unknown_document_agent,
)
from engine.services import ai_provider

if typing.TYPE_CHECKING:
    from engine.agents.data_extraction_agent import ExtractionProvider

_PROVIDERS: tuple[ExtractionProvider, ...] = ("openai", "ollama")


@pytest.fixture(autouse=True)
def _api_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """Give the hosted provider a token so construction is not the thing tested."""
    monkeypatch.setattr(
        ai_provider,
        "get_cloud_token",
        lambda: "test-token-not-used",
    )


@pytest.mark.parametrize("provider", _PROVIDERS)
def test_the_unknown_document_agent_builds(provider: ExtractionProvider) -> None:
    agent = build_unknown_document_agent(provider)

    assert agent.output_type is UnknownDocumentExtractionResult


def test_the_narrative_fact_agent_builds() -> None:
    data_extraction_agent._fact_extraction_agent.cache_clear()  # noqa: SLF001

    assert data_extraction_agent._fact_extraction_agent() is not None  # noqa: SLF001


@pytest.mark.parametrize("provider", _PROVIDERS)
def test_a_schema_violation_is_sent_back_to_the_model(
    provider: ExtractionProvider,
) -> None:
    """One omitted field must not cost a whole 600-token window of a document."""
    agent = build_unknown_document_agent(provider)

    assert agent._max_output_retries > 1  # noqa: SLF001
