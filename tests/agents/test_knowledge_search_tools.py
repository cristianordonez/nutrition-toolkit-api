"""Tests for manual-specific knowledge search tools."""

from __future__ import annotations

import asyncio
import typing
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from pydantic_ai import Agent, FunctionToolset
from pydantic_ai.models.test import TestModel

from ntk.agents.tools.knowledge_search_tools import (
    KNOWLEDGE_SEARCH_TOOLSET,
    KnowledgeSearchToolDependencies,
    RagSearchInput,
    get_knowledge_from_diet_manual,
    get_knowledge_from_nutrition_care_manual,
)
from ntk.models.rag import RagSearchMatch

if typing.TYPE_CHECKING:
    from pydantic_ai.models import ModelRequestParameters

    from ntk.models.knowledge import KnowledgeType
    from ntk.services.embedding_service import EmbeddingService

_SOURCE_PAGE = 44


class FakeEmbeddingService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, int]] = []

    async def search_knowledge(
        self,
        query: str,
        top_k: int,
        *,
        document_type: KnowledgeType,
    ) -> list[RagSearchMatch]:
        self.calls.append((document_type.value, query, top_k))
        return [_match(f"{document_type.value}.pdf", document_type)]


def _match(filename: str, knowledge_type: KnowledgeType) -> RagSearchMatch:
    return RagSearchMatch(
        document_id=1,
        filename=filename,
        chunk_text="Relevant guidance",
        similarity=0.91,
        knowledge_type=knowledge_type,
        section_title="Renal Diet",
        source_page_start=_SOURCE_PAGE,
        source_page_end=_SOURCE_PAGE,
    )


def _context(service: FakeEmbeddingService) -> object:
    dependencies = KnowledgeSearchToolDependencies(
        embedding_service=typing.cast("EmbeddingService", service),
    )
    return SimpleNamespace(deps=dependencies)


def test_nutrition_care_manual_tool_calls_specific_service_method() -> None:
    service = FakeEmbeddingService()

    result = asyncio.run(
        get_knowledge_from_nutrition_care_manual(
            typing.cast("typing.Any", _context(service)),
            RagSearchInput(query=" protein requirements "),
        ),
    )

    assert service.calls == [("nutrition-care-manual", "protein requirements", 3)]
    assert result["source"] == "nutrition-care-manual"
    assert result["matches"][0]["filename"] == "nutrition-care-manual.pdf"  # ty: ignore[not-subscriptable]
    assert result["matches"][0]["source_page_start"] == _SOURCE_PAGE  # ty: ignore[not-subscriptable]


def test_diet_manual_tool_calls_specific_service_method() -> None:
    service = FakeEmbeddingService()

    result = asyncio.run(
        get_knowledge_from_diet_manual(
            typing.cast("typing.Any", _context(service)),
            RagSearchInput(query="renal diet restrictions"),
        ),
    )

    assert service.calls == [("diet-manual", "renal diet restrictions", 3)]
    assert result["source"] == "diet-manual"
    assert result["matches"][0]["filename"] == "diet-manual.pdf"  # ty: ignore[not-subscriptable]


def test_search_input_rejects_whitespace_only_query() -> None:
    with pytest.raises(ValidationError, match="Search query must not be empty"):
        RagSearchInput(query=" \n\t ")


def test_both_manual_search_tools_are_registered_with_clear_descriptions() -> None:
    assert isinstance(KNOWLEDGE_SEARCH_TOOLSET, FunctionToolset)
    service = FakeEmbeddingService()
    model = TestModel(call_tools=[], custom_output_text="done")
    Agent(
        model,
        output_type=str,
        deps_type=KnowledgeSearchToolDependencies,
        toolsets=[KNOWLEDGE_SEARCH_TOOLSET],
    ).run_sync(
        "Inspect knowledge tools",
        deps=KnowledgeSearchToolDependencies(
            embedding_service=typing.cast("EmbeddingService", service),
        ),
    )
    request_parameters = typing.cast(
        "ModelRequestParameters",
        model.last_model_request_parameters,
    )
    tools = {tool.name: tool for tool in request_parameters.function_tools}

    assert set(tools) == {
        "get_knowledge_from_diet_manual",
        "get_knowledge_from_nutrition_care_manual",
    }
    diet_description = tools["get_knowledge_from_diet_manual"].description
    nutrition_description = tools[
        "get_knowledge_from_nutrition_care_manual"
    ].description
    assert diet_description is not None
    assert nutrition_description is not None
    assert "diet-order definitions" in diet_description
    assert "clinical nutrition assessment" in nutrition_description
