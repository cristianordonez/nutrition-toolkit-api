"""Controller group for semantic search commands."""

from __future__ import annotations

import typing

from ntk.controllers.base import BaseControllerGroup
from ntk.controllers.registry import register_command_group
from ntk.controllers.search.assessment import AssessmentSearchController
from ntk.controllers.search.knowledge import KnowledgeVectorSearchController


@register_command_group
class SearchControllerGroup(BaseControllerGroup):
    """Expose semantic search commands by resource type."""

    name = "search"
    help = "Search indexed content"

    def __init__(self) -> None:
        """Initialize search subcommands."""
        self._subcommands = [
            AssessmentSearchController(),
            KnowledgeVectorSearchController(),
        ]

    @property
    def subcommands(self) -> list[typing.Any]:
        """Return commands available under ``search``."""
        return self._subcommands
