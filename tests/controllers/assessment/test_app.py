from __future__ import annotations

from ntk.controllers.assessment.app import AssessmentControllerGroup
from ntk.controllers.assessment.generate import GenerateController
from ntk.controllers.assessment.ingest import AssessmentIngestController
from ntk.controllers.assessment.search import AssessmentSearchController
from ntk.controllers.registry import COMMAND_REGISTRY

_SUBCOMMAND_COUNT = 3


def test_assessment_controller_group_registration_and_subcommands() -> None:
    group = AssessmentControllerGroup()

    assert COMMAND_REGISTRY["assessment"] is AssessmentControllerGroup
    assert len(group.subcommands) == _SUBCOMMAND_COUNT
    assert isinstance(group.subcommands[0], GenerateController)
    assert isinstance(group.subcommands[1], AssessmentIngestController)
    assert isinstance(group.subcommands[2], AssessmentSearchController)
