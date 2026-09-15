r"""Developer workflow: extract local documents, print NCP-generation requests.

Replaces the old (pre-split) one-call browser demo, which ran extraction and
generation in a single process -- that stopped being possible once
extraction (device) and generation (cloud) became separate apps/processes
(see the split refactor plan, decision 8). This command runs the real
extraction pipeline and prints the exact JSON payload the real
``POST /nutrition-care-processes/generate`` endpoint expects for each
affected person, so a developer can pipe it into ``curl`` against a running
cloud-api instance:

    engine demo build-context report.pdf > context.json
    curl -X POST $CLOUD_API_URL/nutrition-care-processes/generate \
        -H 'content-type: application/json' -d @context.json
"""

# Pydantic resolves these annotation types at runtime when building model schemas.
# ruff: noqa: TC003

from __future__ import annotations

import json
import pathlib
import typing

from pydantic import BaseModel, Field

from engine.controllers.session import controller_session
from engine.pipelines.ncp.create.context_budgeter import ContextBudgeter
from engine.pipelines.person.ingestion.pipeline import PersonIngestionPipeline
from engine.repositories.clinical_note_repo import ClinicalNoteRepo
from engine.repositories.facility_repo import FacilityRepo
from engine.repositories.person_repo import PersonRepo
from engine.services.facility_resolver import FacilityResolver
from engine.services.person.person_service import PersonService
from ntk.controllers.base import BaseController
from ntk.models.base import ConsoleRenderableModel
from ntk.models.ncp_context import NCPGenerationRequest  # noqa: TC001
from ntk.models.output import Output

if typing.TYPE_CHECKING:
    from sqlmodel import Session


class BuildContextOptions(BaseModel):
    """Local documents to extract before building generation requests."""

    files: list[pathlib.Path] = Field(min_length=1)
    additional_context: str | None = None


class BuildContextResult(ConsoleRenderableModel):
    """One NCP-generation request per person affected by the ingested files."""

    requests: list[NCPGenerationRequest]

    def to_console(self) -> str:
        """Print one JSON generation request per line."""
        return "\n".join(
            json.dumps(json.loads(request.model_dump_json()))
            for request in self.requests
        )


class BuildContextController(BaseController):
    """Ingest local documents and print the resulting generation requests."""

    name = "build-context"
    help = "Extract local documents and print NCP-generation request JSON"
    options_model = BuildContextOptions

    def __init__(self, session: Session | None = None) -> None:
        """Store the optional controller-owned session."""
        self.session = session

    async def run(
        self,
        options: BuildContextOptions,
    ) -> Output[BuildContextResult]:
        """Extract the supplied documents and build one request per person."""
        with controller_session(self.session) as session:
            facility_resolver = FacilityResolver(FacilityRepo(session))
            person_service = PersonService(
                PersonRepo(session),
                facility_resolver,
            )
            pipeline = PersonIngestionPipeline(
                clinical_note_repository=ClinicalNoteRepo(session),
                person_service=person_service,
                facility_resolver=facility_resolver,
            )
            result = await pipeline.ingest(files=options.files)
            person_ids = sorted(
                {
                    fact.person_id
                    for document in result.documents
                    for fact in document.extracted_facts
                    if fact.person_id is not None
                },
            )
            budgeter = ContextBudgeter()
            requests = [
                budgeter.budget(
                    person_service.get_person_detail_by_id(person_id),
                    additional_context=options.additional_context,
                ).request
                for person_id in person_ids
            ]
        return Output(
            result=BuildContextResult(requests=requests),
            controller=self.name,
            exit_code=0,
        )


__all__ = [
    "BuildContextController",
    "BuildContextOptions",
    "BuildContextResult",
]
