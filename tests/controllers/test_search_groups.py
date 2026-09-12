from __future__ import annotations

import argparse

from ntk.controllers.assessment.app import AssessmentControllerGroup
from ntk.controllers.assessment.search import (
    AssessmentSearchController,
    AssessmentSearchOptions,
)
from ntk.controllers.knowledge.app import KnowledgeControllerGroup
from ntk.controllers.knowledge.search import (
    KnowledgeSearchOptions,
    KnowledgeVectorSearchController,
)


def test_search_controllers_belong_to_resource_groups() -> None:
    assessment_search = AssessmentControllerGroup().subcommands[-1]
    knowledge_search = KnowledgeControllerGroup().subcommands[-1]

    assert isinstance(assessment_search, AssessmentSearchController)
    assert assessment_search.name == "search"
    assert isinstance(knowledge_search, KnowledgeVectorSearchController)
    assert knowledge_search.name == "search"


def test_resource_groups_register_search_cli_paths() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    AssessmentControllerGroup().register(subparsers)
    KnowledgeControllerGroup().register(subparsers)

    assessments = parser.parse_args(
        ["assessment", "search", "--text", "weight loss"],
    )
    knowledge = parser.parse_args(
        ["knowledge", "search", "--text", "protein needs"],
    )

    assert assessments.options_model is AssessmentSearchOptions
    assert knowledge.options_model is KnowledgeSearchOptions
