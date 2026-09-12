"""Controller group for all commands under assessment."""

from __future__ import annotations

import logging
import typing

from ntk.controllers.assessment.finalize import (
    AssessmentFinalizeCommandController,
)
from ntk.controllers.assessment.get import AssessmentGetCommandController
from ntk.controllers.assessment.import_assessments import AssessmentImportController
from ntk.controllers.assessment.search import AssessmentSearchController
from ntk.controllers.base import BaseControllerGroup
from ntk.controllers.registry import register_command_group

logger = logging.getLogger(__name__)


@register_command_group
class AssessmentControllerGroup(BaseControllerGroup):
    """Expose assessment management commands."""

    name = "assessment"
    help = "Manage nutrition assessments"

    def __init__(self) -> None:
        """Initialize class."""
        self._subcommands = [
            AssessmentFinalizeCommandController(),
            AssessmentGetCommandController(),
            AssessmentImportController(),
            AssessmentSearchController(),
        ]

    @property
    def subcommands(self) -> list[typing.Any]:
        """Return the commands available under ``assessment``."""
        return self._subcommands
