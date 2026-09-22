"""Generate a Nutrition Care Process for an already-ingested person.

Generation belongs cloud-side: cloud-api owns the note record and the diet and
nutrition-care manual lookups, which search a knowledge base that only exists
there. So this posts the request to cloud-api by default.

``use_local_generation`` runs the note agent in this process instead. That is a
development and offline escape hatch, not the production path -- it needs no
server, database, or API key, but produces notes without the manual lookups.

Either way the request itself is built here from persisted data, and unlike
``demo build-context`` no files are re-ingested.
"""

from __future__ import annotations

import typing

from pydantic import BaseModel, Field

from engine.agents.ncp_agent import LocalNCPAgent
from engine.clients.cloud_api_client import CloudAPIClient
from engine.controllers.session import controller_session
from engine.models.settings import SETTINGS
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

    from ntk.models.ncp_context import NCPGenerationRequest


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
    generated_by: str

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
        client: CloudAPIClient | None = None,
        agent: LocalNCPAgent | None = None,
    ) -> None:
        """Store the session and both generation backends."""
        self.session = session
        self.client = client
        self.agent = agent

    async def run(
        self,
        options: NCPGenerateOptions,
    ) -> Output[NCPGenerateResult]:
        """Build this person's request and generate the note."""
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

        note_text, generated_by = await self._generate(request)
        return Output(
            result=NCPGenerateResult(
                person_id=options.person_id,
                person_name=request.person.name,
                person_identifier=request.person_identifier,
                note_text=note_text,
                generated_by=generated_by,
            ),
            controller=self.name,
            exit_code=0,
        )

    async def _generate(self, request: NCPGenerationRequest) -> tuple[str, str]:
        """Generate the note, reporting which backend produced it."""
        if self.agent is not None or SETTINGS.use_local_generation:
            agent = self.agent or LocalNCPAgent()
            return await agent.run(request), "local"
        client = self.client or CloudAPIClient(
            str(SETTINGS.cloud_api_base_url),
            api_key=SETTINGS.cloud_api_key,
        )
        ncp = await client.generate_ncp(request)
        return ncp.note_text, "cloud-api"


__all__ = [
    "NCPGenerateController",
    "NCPGenerateOptions",
    "NCPGenerateResult",
]
