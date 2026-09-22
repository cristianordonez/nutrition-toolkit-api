"""Generate a Nutrition Care Process for an already-ingested person.

Composes the person's persisted detail, the deterministic context budgeter
that builds the request, and the on-device note agent. Generation runs in this
process against OpenAI, so no cloud-api server, database, or API key is
involved. Unlike ``demo build-context`` this does not re-ingest any files.
"""

from __future__ import annotations

import typing

from pydantic import BaseModel, Field

from engine.agents.ncp_agent import LocalNCPAgent
from engine.controllers.session import controller_session
from engine.pipelines.ncp.create.context_budgeter import ContextBudgeter
from engine.repositories.facility_repo import FacilityRepo
from engine.repositories.person_repo import PersonRepo
from engine.services.facility_resolver import FacilityResolver
from engine.services.person.person_service import PersonService
from ntk.controllers.base import BaseController
from ntk.models.base import ConsoleRenderableModel
from ntk.models.output import Output

if typing.TYPE_CHECKING:
    from sqlmodel import Session


class NCPGenerateOptions(BaseModel):
    """The resident to generate a Nutrition Care Process for."""

    person_id: int = Field(description="Internal person database ID")
    additional_context: str | None = Field(
        default=None,
        description="Optional runtime focus for this note",
    )


class NCPGenerateResult(ConsoleRenderableModel):
    """The generated Nutrition Care Process note."""

    person_id: int
    person_name: str
    person_identifier: str
    note_text: str

    def to_console(self) -> str:
        """Render the generated note as formatted JSON."""
        return self.model_dump_json(indent=2)


class NCPGenerateController(BaseController):
    """Generate a Nutrition Care Process for one persisted person."""

    name = "generate"
    help = "Generate a Nutrition Care Process note for a person"
    options_model = NCPGenerateOptions

    def __init__(
        self,
        session: Session | None = None,
        agent: LocalNCPAgent | None = None,
    ) -> None:
        """Store the optional session and the on-device note agent."""
        self.session = session
        self.agent = agent or LocalNCPAgent()

    async def run(
        self,
        options: NCPGenerateOptions,
    ) -> Output[NCPGenerateResult]:
        """Build this person's generation request and generate the note."""
        with controller_session(self.session) as session:
            person_service = PersonService(
                PersonRepo(session),
                FacilityResolver(FacilityRepo(session)),
            )
            detail = person_service.get_person_detail_by_id(options.person_id)
            request = (
                ContextBudgeter()
                .budget(detail, additional_context=options.additional_context)
                .request
            )
        note_text = await self.agent.run(request)
        return Output(
            result=NCPGenerateResult(
                person_id=options.person_id,
                person_name=request.person.name,
                person_identifier=request.person_identifier,
                note_text=note_text,
            ),
            controller=self.name,
            exit_code=0,
        )


__all__ = [
    "NCPGenerateController",
    "NCPGenerateOptions",
    "NCPGenerateResult",
]
