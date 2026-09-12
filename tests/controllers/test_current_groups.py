from __future__ import annotations

import asyncio

import pytest

from ntk.controllers.assessment.app import AssessmentControllerGroup
from ntk.controllers.documents.app import DocumentControllerGroup
from ntk.controllers.food.app import FoodControllerGroup
from ntk.controllers.food.sync import (
    FoodSyncController,
    FoodSyncOptions,
    FoodSyncResponse,
)
from ntk.controllers.knowledge.app import KnowledgeControllerGroup
from ntk.models.sql.knowledge import Knowledge


def test_current_controller_groups_expose_their_commands() -> None:
    assessment = AssessmentControllerGroup()
    documents = DocumentControllerGroup()
    food = FoodControllerGroup()
    knowledge = KnowledgeControllerGroup()

    assert len(assessment.subcommands) == 4  # noqa: PLR2004
    assert len(documents.subcommands) == 1
    assert food.subcommands == []
    assert len(knowledge.subcommands) == 2  # noqa: PLR2004


def test_food_sync_response_renders_documents() -> None:
    response = FoodSyncResponse(
        documents=[
            Knowledge(
                filename="foods.json",
                knowledge_type="nutrition-care-manual",
                file_hash="hash",
            ),
        ],
    )

    assert response.to_console() == "# foods.json"


def test_food_sync_explicitly_reports_not_implemented() -> None:
    controller = FoodSyncController()

    with pytest.raises(NotImplementedError, match="not implemented"):
        asyncio.run(controller.run(FoodSyncOptions(overwrite=True)))
