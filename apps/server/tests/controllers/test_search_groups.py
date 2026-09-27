from __future__ import annotations

import argparse

from server.controllers.knowledge.app import KnowledgeControllerGroup
from server.controllers.knowledge.search import (
    KnowledgeSearchOptions,
    KnowledgeVectorSearchController,
)
from server.controllers.ncp.app import NCPControllerGroup
from server.controllers.ncp.search import (
    NCPSearchController,
    NCPSearchOptions,
)


def test_search_controllers_belong_to_resource_groups() -> None:
    ncp_search = NCPControllerGroup().subcommands[-1]
    knowledge_search = KnowledgeControllerGroup().subcommands[-1]

    assert isinstance(ncp_search, NCPSearchController)
    assert ncp_search.name == "search"
    assert isinstance(knowledge_search, KnowledgeVectorSearchController)
    assert knowledge_search.name == "search"


def test_resource_groups_register_search_cli_paths() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    NCPControllerGroup().register(subparsers)
    KnowledgeControllerGroup().register(subparsers)

    ncps = parser.parse_args(
        [
            "ncp",
            "search",
            "--text",
            "weight loss",
            "--person-identifier",
            "person-1",
        ],
    )
    knowledge = parser.parse_args(
        ["knowledge", "search", "--text", "protein needs"],
    )

    assert ncps.options_model is NCPSearchOptions
    assert knowledge.options_model is KnowledgeSearchOptions
