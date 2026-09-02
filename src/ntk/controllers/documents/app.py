"""Controller group for document commands."""

from __future__ import annotations

import typing

from ntk.controllers.base import BaseControllerGroup
from ntk.controllers.documents.ingest import DocumentIngestController
from ntk.controllers.registry import register_command_group


@register_command_group
class DocumentControllerGroup(BaseControllerGroup):
    """Expose document ingestion commands."""

    name = "document"
    help = "Ingest documents"

    def __init__(self) -> None:
        """Initialize document subcommands."""
        self._subcommands = [DocumentIngestController()]

    @property
    def subcommands(self) -> list[typing.Any]:
        """Return commands available under ``document``."""
        return self._subcommands
