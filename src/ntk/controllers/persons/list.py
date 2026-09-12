"""List persisted persons."""

from __future__ import annotations

import typing

from pydantic import BaseModel

from ntk.controllers.base import BaseController
from ntk.controllers.session import controller_session
from ntk.models.output import Output
from ntk.models.sql.person import Person  # noqa: TC001
from ntk.repositories.person_repo import PersonRepo

if typing.TYPE_CHECKING:
    from sqlmodel import Session


class PersonListOptions(BaseModel):
    """Options for listing persons."""


class PersonListResult(BaseModel):
    """Persisted persons."""

    persons: list[Person]


class PersonListController(BaseController):
    """Return all persisted persons."""

    name = "list"
    help = "List persons"
    options_model = PersonListOptions

    def __init__(self, session: Session | None = None) -> None:
        """Store the optional controller-owned session."""
        self.session = session

    def run(self, options: PersonListOptions) -> Output[PersonListResult]:
        """Return all persons."""
        del options
        with controller_session(self.session) as session:
            persons = PersonRepo(session).get_all()
        return Output(
            result=PersonListResult(persons=persons),
            controller=self.name,
            exit_code=0,
        )


__all__ = ["PersonListController", "PersonListOptions", "PersonListResult"]
