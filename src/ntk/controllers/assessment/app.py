"""Controller group for all commands under assessment."""

from __future__ import annotations

import logging
import typing

from ntk.controllers.assessment.generate import GenerateController
from ntk.controllers.assessment.ingest import AssessmentIngestController
from ntk.controllers.assessment.search import AssessmentSearchController
from ntk.controllers.base import BaseControllerGroup
from ntk.controllers.registry import register_command_group

logger = logging.getLogger(__name__)


@register_command_group
class AssessmentControllerGroup(BaseControllerGroup):
    """Expose assessment generation and ingestion commands."""

    name = "assessment"
    help = "Generate and ingest nutrition assessments"

    def __init__(self) -> None:
        """Initialize class."""
        self._subcommands = [
            GenerateController(),
            AssessmentIngestController(),
            AssessmentSearchController(),
        ]

    @property
    def subcommands(self) -> list[typing.Any]:
        """Return the commands available under ``assessment``."""
        return self._subcommands
