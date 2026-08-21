from __future__ import annotations

from ntk.controllers.assessment.app import AssessmentControllerGroup
from ntk.controllers.calculate.energy import EnergyController
from ntk.controllers.registry import COMMAND_REGISTRY


def test_assessment_controller_group_registration_and_subcommands() -> None:
    group = AssessmentControllerGroup()

    assert COMMAND_REGISTRY["assessment"] is AssessmentControllerGroup
    assert len(group.subcommands) == 1
    assert isinstance(group.subcommands[0], EnergyController)
