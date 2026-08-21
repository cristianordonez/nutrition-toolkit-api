"""Controller group for retrieval-augmented generation commands."""

from __future__ import annotations

import typing

from ntk.controllers.base import BaseControllerGroup
from ntk.controllers.rag.ingest import IngestController
from ntk.controllers.registry import register_command


@register_command()
class RagControllerGroup(BaseControllerGroup):
    """Expose RAG document preparation commands through the CLI."""

    name = "rag"
    help = "Retrieval-augmented generation controller group"

    def __init__(self) -> None:
        """Initialize the RAG subcommands."""
        self._subcommands = [IngestController()]

    @property
    def subcommands(self) -> list[typing.Any]:
        """Return the commands available under ``rag``."""
        return self._subcommands
