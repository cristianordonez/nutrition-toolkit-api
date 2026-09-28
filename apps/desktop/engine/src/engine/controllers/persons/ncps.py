"""Return the NCP notes held on this device for one person."""

from __future__ import annotations

import typing

from pydantic import BaseModel, Field

from engine.controllers.base import BaseController
from engine.database.sessions import controller_session
from engine.models.base import ConsoleRenderableModel
from engine.models.output import Output
from engine.models.sql.ncp_note import NCPNote  # noqa: TC001
from engine.repositories.ncp_note_repo import NCPNoteRepo
from engine.repositories.person_repo import PersonRepo

if typing.TYPE_CHECKING:
    from sqlmodel import Session


class PersonNCPsOptions(BaseModel):
    """Person identifier whose clinical notes should be returned."""

    person_identifier: str = Field(
        min_length=1,
        description="The person's external identifier",
    )


class PersonNCPsResult(ConsoleRenderableModel):
    """Clinical notes belonging to the requested person."""

    ncps: list[NCPNote]

    def to_console(self) -> str:
        """Render notes as formatted JSON."""
        return self.model_dump_json(indent=2)


class PersonNCPsController(BaseController):
    """Retrieve one person's locally stored clinical notes."""

    name = "ncps"
    help = "Get clinical notes by person identifier"
    options_model = PersonNCPsOptions

    def __init__(self, session: Session | None = None) -> None:
        """Store the optional controller-owned session."""
        self.session = session

    def run(self, options: PersonNCPsOptions) -> Output[PersonNCPsResult]:
        """Return the notes stored for the supplied person identifier."""
        with controller_session(self.session) as session:
            person = PersonRepo(session).get_by_identifier(
                options.person_identifier,
            )
            # An unknown identifier is an empty history, not an error: the
            # caller asked what is on file, and the answer is nothing.
            notes = (
                NCPNoteRepo(session).list_for_person(person.id)
                if person is not None and person.id is not None
                else []
            )
        return Output(
            result=PersonNCPsResult(ncps=notes),
            controller=self.name,
            exit_code=0,
        )


__all__ = [
    "PersonNCPsController",
    "PersonNCPsOptions",
    "PersonNCPsResult",
]
