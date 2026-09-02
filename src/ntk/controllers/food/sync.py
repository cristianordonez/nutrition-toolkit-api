"""Sync nutrition data from API."""

from __future__ import annotations

import typing

from pydantic import BaseModel, Field

from ntk.controllers.base import BaseController
from ntk.models.base import ConsoleRenderableModel
from ntk.models.sql.knowledge import Knowledge  # noqa: TC001

if typing.TYPE_CHECKING:
    from sqlmodel import Session

    from ntk.models.output import Output


class FoodSyncOptions(BaseModel):
    """Options for ingesting clinical knowledge documents."""

    overwrite: bool = Field(default=False, description="Replace existing documents")


class FoodSyncResponse(ConsoleRenderableModel):
    """Sync API to database."""

    documents: list[Knowledge]

    def to_console(self) -> str:
        """Render the names of ingested knowledge documents."""
        return "\n".join(f"# {document.filename}" for document in self.documents)


class FoodSyncController(BaseController):
    """Store knowledge documents and their embeddings."""

    name = "food"
    help = "Sync API data to database"
    options_model = FoodSyncOptions

    def __init__(self, session: Session | None = None) -> None:
        """Use an injected session or create one for each controller run."""
        self.session = session

    async def run(
        self,
        options: FoodSyncOptions,
    ) -> Output[FoodSyncResponse]:
        """Reject food sync until its external-data contract is implemented."""
        del options
        msg = "Food synchronization is not implemented"
        raise NotImplementedError(msg)
