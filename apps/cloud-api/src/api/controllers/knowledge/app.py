"""Controller group for clinical knowledge commands."""

from __future__ import annotations

import typing

from api.controllers.knowledge.ingest import KnowledgeIngestController
from api.controllers.knowledge.search import KnowledgeVectorSearchController
from ntk.controllers.base import BaseControllerGroup
from ntk.controllers.registry import register_command_group


@register_command_group
class KnowledgeControllerGroup(BaseControllerGroup):
    """Expose clinical knowledge management commands."""

    name = "knowledge"
    help = "Manage clinical knowledge documents"

    def __init__(self) -> None:
        """Initialize the knowledge subcommands."""
        self._subcommands = [
            KnowledgeIngestController(),
            KnowledgeVectorSearchController(),
        ]

    @property
    def subcommands(self) -> list[typing.Any]:
        """Return commands available under ``knowledge``."""
        return self._subcommands
