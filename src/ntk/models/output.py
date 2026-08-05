"""Output model is returned from all controller run methods."""

from __future__ import annotations

from pydantic import BaseModel

from ntk.models.base import ConsoleRenderableModel  # noqa: TC001


class Output(BaseModel):
    """Output to the run method of controllers."""

    controller: str
    result: ConsoleRenderableModel
    exit_code: int
