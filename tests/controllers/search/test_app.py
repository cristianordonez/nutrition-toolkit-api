from __future__ import annotations

import argparse

from ntk.controllers.registry import COMMAND_REGISTRY
from ntk.controllers.search.app import SearchControllerGroup
from ntk.controllers.search.assessment import (
    AssessmentSearchController,
    AssessmentSearchOptions,
)
from ntk.controllers.search.knowledge import (
    KnowledgeSearchOptions,
    KnowledgeVectorSearchController,
)


def test_search_group_registers_vector_subcommands() -> None:
    group = SearchControllerGroup()

    assert COMMAND_REGISTRY["search"] is SearchControllerGroup
    assert len(group.subcommands) == 2  # noqa: PLR2004
    assert isinstance(group.subcommands[0], AssessmentSearchController)
    assert group.subcommands[0].name == "assessments"
    assert isinstance(group.subcommands[1], KnowledgeVectorSearchController)
    assert group.subcommands[1].name == "knowledge"


def test_search_group_registers_requested_cli_paths() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    SearchControllerGroup().register(subparsers)

    assessments = parser.parse_args(
        ["search", "assessments", "--text", "weight loss"],
    )
    knowledge = parser.parse_args(
        ["search", "knowledge", "--text", "protein needs"],
    )

    assert assessments.options_model is AssessmentSearchOptions
    assert knowledge.options_model is KnowledgeSearchOptions
