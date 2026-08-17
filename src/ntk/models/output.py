"""Output model is returned from all controller run methods."""

from __future__ import annotations

import typing

from pydantic import BaseModel

from ntk.models.base import ConsoleRenderableModel

T = typing.TypeVar("T", bound=ConsoleRenderableModel)


class Output(BaseModel, typing.Generic[T]):
    """Output to the run method of controllers."""

    controller: str
    result: T
    exit_code: int
