"""List persisted residents."""

from __future__ import annotations

import typing

from pydantic import BaseModel

from ntk.controllers.base import BaseController
from ntk.controllers.session import controller_session
from ntk.models.output import Output
from ntk.models.sql.resident import Resident  # noqa: TC001
from ntk.repositories.resident_repo import ResidentRepo

if typing.TYPE_CHECKING:
    from sqlmodel import Session


class ResidentListOptions(BaseModel):
    """Options for listing residents."""


class ResidentListResult(BaseModel):
    """Persisted residents."""

    residents: list[Resident]


class ResidentListController(BaseController):
    """Return all persisted residents."""

    name = "list"
    help = "List residents"
    options_model = ResidentListOptions

    def __init__(self, session: Session | None = None) -> None:
        """Store the optional controller-owned session."""
        self.session = session

    def run(self, options: ResidentListOptions) -> Output[ResidentListResult]:
        """Return all residents."""
        del options
        with controller_session(self.session) as session:
            residents = ResidentRepo(session).get_all()
        return Output(
            result=ResidentListResult(residents=residents),
            controller=self.name,
            exit_code=0,
        )


__all__ = ["ResidentListController", "ResidentListOptions", "ResidentListResult"]
