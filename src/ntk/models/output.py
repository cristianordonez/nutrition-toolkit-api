"""Output model is returned from all controller run methods."""

from __future__ import annotations

import typing

from pydantic import BaseModel


class Output(BaseModel):
    """Output to the run method of controllers."""

    controller: str
    result: typing.Any
    exit_code: int
