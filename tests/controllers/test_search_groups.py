from __future__ import annotations

import argparse

from ntk.controllers.knowledge.app import KnowledgeControllerGroup
from ntk.controllers.knowledge.search import (
    KnowledgeSearchOptions,
    KnowledgeVectorSearchController,
)
from ntk.controllers.ncp.app import NCPControllerGroup
from ntk.controllers.ncp.search import (
    NCPSearchController,
    NCPSearchOptions,
)


def test_search_controllers_belong_to_resource_groups() -> None:
    assessment_search = NCPControllerGroup().subcommands[-1]
    knowledge_search = KnowledgeControllerGroup().subcommands[-1]

    assert isinstance(assessment_search, NCPSearchController)
    assert assessment_search.name == "search"
    assert isinstance(knowledge_search, KnowledgeVectorSearchController)
    assert knowledge_search.name == "search"


def test_resource_groups_register_search_cli_paths() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    NCPControllerGroup().register(subparsers)
    KnowledgeControllerGroup().register(subparsers)

    ncps = parser.parse_args(
        ["ncp", "search", "--text", "weight loss"],
    )
    knowledge = parser.parse_args(
        ["knowledge", "search", "--text", "protein needs"],
    )

    assert ncps.options_model is NCPSearchOptions
    assert knowledge.options_model is KnowledgeSearchOptions
