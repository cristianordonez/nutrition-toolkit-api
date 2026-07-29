"""Output model is returned from all controller run methods."""

from __future__ import annotations

from pydantic import BaseModel


class Output(BaseModel):
    """Output to the run method of controllers."""

    controller: str
    result: BaseModel
    exit_code: int
