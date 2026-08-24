"""Generate a nutrition assessment from resident PDF or CSV files."""

from __future__ import annotations

import asyncio
import pathlib  # noqa: TC003
import typing

from pydantic import BaseModel, Field

from ntk.agents.assessment_agent import AdmissionAgent
from ntk.agents.resident_data_agent import ResidentDataAgent
from ntk.controllers.assessment.search import (
    AssessmentSearchController,
    AssessmentSearchOptions,
)
from ntk.controllers.base import BaseController
from ntk.controllers.knowledge.search import (
    KnowledgeSearchController,
    KnowledgeSearchOptions,
)
from ntk.controllers.uploads import (
    ReadableUpload,
    UploadRequirements,
    materialize_uploads,
)
from ntk.models.output import Output

if typing.TYPE_CHECKING:
    from ntk.models.sql.assessment import Assessment


class GenerateOptions(BaseModel):
    """Options for generating a nutrition assessment."""

    files: list[pathlib.Path] = Field(
        description="One or more resident PDF or CSV files",
    )
    context: str | None = Field(
        default=None,
        description="Optional assessment focus or additional resident context",
    )


class GenerateController(BaseController):
    """Extract resident data, retrieve context, and create an assessment."""

    name = "generate"
    help = "Generate a nutrition assessment from resident PDF or CSV files"
    options_model = GenerateOptions

    def __init__(
        self,
        resident_data_agent: ResidentDataAgent | None = None,
        admission_agent: AdmissionAgent | None = None,
        knowledge_search: KnowledgeSearchController | None = None,
        assessment_search: AssessmentSearchController | None = None,
    ) -> None:
        """Initialize optional extraction, retrieval, and generation dependencies."""
        self.resident_data_agent = resident_data_agent
        self.admission_agent = admission_agent
        self.knowledge_search = knowledge_search
        self.assessment_search = assessment_search

    async def run_uploads(
        self,
        files: typing.Sequence[ReadableUpload],
        context: str | None = None,
    ) -> Output[Assessment]:
        """Validate uploaded resident files and generate an assessment."""
        async with materialize_uploads(
            files,
            UploadRequirements(
                allowed_suffixes=frozenset({".csv", ".pdf"}),
                file_description="PDF or CSV file",
                directory_prefix="ntk-generate-",
                default_filename=lambda index: f"resident-{index + 1}.pdf",
                reject_empty=True,
            ),
        ) as uploads:
            return await self.run(
                GenerateOptions(files=uploads.paths, context=context),
            )

    async def run(self, options: GenerateOptions) -> Output[Assessment]:
        """Extract data, retrieve evidence and examples, then generate a note."""
        resident_agent = self.resident_data_agent or ResidentDataAgent()
        resident_data = await resident_agent.extract(options.files, options.context)
        retrieval_query = self._retrieval_query(
            resident_data.to_console(),
            options.context,
        )
        # get patient context
        # use context to get deterministic calculations, progress note selection
        # get knowledge
        # get deidentified style examples
        # send to agent to make assessment
        knowledge_search = self.knowledge_search or KnowledgeSearchController()
        assessment_search = self.assessment_search or AssessmentSearchController()
        knowledge_output, assessment_output = await asyncio.gather(
            asyncio.to_thread(
                knowledge_search.run,
                KnowledgeSearchOptions(text=retrieval_query),
            ),
            asyncio.to_thread(
                assessment_search.run,
                AssessmentSearchOptions(text=retrieval_query),
            ),
        )
        knowledge = knowledge_output.result.matches
        previous_assessments = assessment_output.result.matches
        admission_agent = self.admission_agent or AdmissionAgent()
        assessment = await admission_agent.generate(
            resident_data,
            knowledge,
            previous_assessments,
            options.context,
        )
        return Output(result=assessment, controller=self.name, exit_code=0)

    @staticmethod
    def _retrieval_query(resident_data: str, context: str | None) -> str:
        """Build the semantic query from current resident facts and user focus."""
        if context and context.strip():
            return f"{context.strip()}\n{resident_data}"
        return resident_data
