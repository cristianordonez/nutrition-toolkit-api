"""Controller group for clinical knowledge commands."""

from __future__ import annotations

import typing

from ntk.controllers.base import BaseControllerGroup
from ntk.controllers.knowledge.ingest import KnowledgeIngestController
from ntk.controllers.registry import register_command_group


@register_command_group
class KnowledgeControllerGroup(BaseControllerGroup):
    """Expose clinical knowledge ingestion commands."""

    name = "knowledge"
    help = "Manage clinical knowledge documents"

    def __init__(self) -> None:
        """Initialize the knowledge subcommands."""
        self._subcommands = [KnowledgeIngestController()]

    @property
    def subcommands(self) -> list[typing.Any]:
        """Return commands available under ``knowledge``."""
        return self._subcommands
