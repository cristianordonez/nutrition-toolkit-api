"""Generate a Nutrition Care Process for an already-ingested person.

Generation runs on this device, where the resident's record already lives, so
no clinical data leaves the machine unless the user has explicitly switched on
a hosted model in Settings and supplied their own API token.

The request is built here from persisted data, and unlike
``demo build-context`` no files are re-ingested.
"""

from __future__ import annotations

import typing

from pydantic import BaseModel, Field

from engine.agents.ncp_agent import NCPAgent
from engine.controllers.base import BaseController
from engine.database.sessions import controller_session
from engine.models.base import ConsoleRenderableModel
from engine.models.ncp_note import NCPNoteStatus, NCPNoteType
from engine.models.output import Output
from engine.models.sql.ncp_note import NCPNote
from engine.pipelines.ncp.create.context_budgeter import ContextBudgeter
from engine.repositories.ncp_note_repo import NCPNoteRepo
from engine.repositories.person_repo import PersonRepo
from engine.services.ai.controller import selected_provider
from engine.services.embedding_service import EmbeddingService
from engine.services.note_retrieval import NoteRetrievalService
from engine.services.person.person_service import PersonService

if typing.TYPE_CHECKING:
    from sqlmodel import Session

    from engine.models.ncp_context import NCPGenerationRequest


class NCPGenerateOptions(BaseModel):
    """The resident to generate a Nutrition Care Process for."""

    person_id: int = Field(description="Internal person database ID")
    note_type: NCPNoteType = Field(description="NCP assessment category")
    additional_context: str | None = Field(
        default=None,
        description="Optional runtime focus for this note",
    )


class NCPGenerateResult(ConsoleRenderableModel):
    """The generated Nutrition Care Process note."""

    person_id: int
    person_name: str
    person_identifier: str
    ncp_note_id: int
    note_type: NCPNoteType
    note_text: str
    status: NCPNoteStatus
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
        agent: NCPAgent | None = None,
        retrieval: NoteRetrievalService | None = None,
    ) -> None:
        """Store the session, the note agent, and prior-note retrieval."""
        self.session = session
        self.agent = agent
        self.retrieval = retrieval

    async def run(
        self,
        options: NCPGenerateOptions,
    ) -> Output[NCPGenerateResult]:
        """Build this person's request and generate the note."""
        with controller_session(self.session) as session:
            person_repository = PersonRepo(session)
            person = person_repository.get_by_id(options.person_id)
            if person is None:
                msg = f"Person {options.person_id} was not found"
                raise ValueError(msg)
            person_service = PersonService(person_repository)
            detail = person_service.get_person_detail_by_id(options.person_id)
            request = (
                ContextBudgeter()
                .budget(
                    detail,
                    note_type=options.note_type,
                    additional_context=options.additional_context,
                )
                .request
            )
            # Inside the session: retrieval reads prior NCPs and writes any
            # missing embeddings for explicit style examples.
            retrieval = self.retrieval or NoteRetrievalService(session)
            request.previous_ncp = retrieval.previous_note(options.person_id)
            request.relevant_ncps = await retrieval.style_examples(
                request.summary_text,
            )

        note_text, generated_by = await self._generate(request)
        with controller_session(self.session) as session:
            note = NCPNoteRepo(session).save(
                NCPNote(
                    person_id=options.person_id,
                    facility_id=person.facility_id,
                    note_type=options.note_type,
                    content=note_text,
                    status=NCPNoteStatus.DRAFT,
                ),
            )
        if note.id is None:
            msg = "Generated NCP draft did not receive a database ID"
            raise RuntimeError(msg)
        return Output(
            result=NCPGenerateResult(
                person_id=options.person_id,
                person_name=request.person.name,
                person_identifier=request.person_identifier,
                ncp_note_id=note.id,
                note_type=note.note_type,
                note_text=note_text,
                status=note.status,
                generated_by=generated_by,
            ),
            controller=self.name,
            exit_code=0,
        )

    async def _generate(self, request: NCPGenerationRequest) -> tuple[str, str]:
        """Generate the note here, reporting which model produced it.

        The agent's manual lookups search the local knowledge base, so it runs
        inside a session of its own rather than the one that built the request.
        """
        with controller_session(self.session) as session:
            agent = self.agent or NCPAgent(
                knowledge_service=EmbeddingService(session),
            )
            note = await agent.run(request)
        return note, selected_provider()


__all__ = [
    "NCPGenerateController",
    "NCPGenerateOptions",
    "NCPGenerateResult",
]
