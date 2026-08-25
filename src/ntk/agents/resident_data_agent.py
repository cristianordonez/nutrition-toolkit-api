"""Agent for merging deterministic file extraction into resident context."""

from __future__ import annotations

import dataclasses
import json
import typing

import logfire
import pymupdf
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider

from ntk.models.settings import SETTINGS
from ntk.models.sql.resident import (
    CsvWoundReportExtraction,
    PccLabReportExtraction,
    PccOrderReportExtraction,
    PccProgressNotesExtraction,
    PccWeightVitalsExtraction,
    ResidentContext,
    ResidentExtraction,
)
from ntk.repositories import ResidentRepo
from ntk.services.document import DocumentExtractorService

if typing.TYPE_CHECKING:
    import pathlib

    from ntk.services.document.extractors.base import BaseExtractor


logfire.configure()
logfire.instrument_pydantic_ai()

RESIDENT_DATA_MODEL = "gpt-5.6-luna"
RESIDENT_DATA_INSTRUCTIONS = """
Build one ResidentContext from deterministic extraction plus files that require
additional review.

Workflow:
1. The prompt contains a ResidentContext populated by deterministic extractors.
   Preserve those facts and their source details.
2. Read only file_ids listed as available for additional review. This includes
   unknown file formats and PCC progress-note reports, whose structured notes were
   extracted deterministically but may contain additional resident facts.
3. Merge explicit facts from those files and supplementary user context into the
   supplied ResidentContext. Never write to a database.
4. Do not replace deterministic facts. Record incompatible supported values in
   conflicts as DataConflict objects.
5. Never invent source identifiers or clinical facts.

Use null for missing scalar values and empty lists for missing collections. Preserve
diagnoses, weights, labs, order wording, wounds, allergies, intake, diet, edema,
dialysis, and nutrition-support details exactly when they are stated by a source.
""".strip()

_SUPPORTED_SUFFIXES = frozenset({".csv", ".pdf"})
_EXTRACTION_TYPE_BY_EXTRACTOR = {
    "PccWeightHistoryExtractor": PccWeightVitalsExtraction,
    "PccProgressNotesExtractor": PccProgressNotesExtraction,
    "PccLabResultsExtractor": PccLabReportExtraction,
    "WoundReportExtractor": CsvWoundReportExtraction,
    "PccOrderReportExtractor": PccOrderReportExtraction,
}


@dataclasses.dataclass(frozen=True)
class ResidentFileSource:
    """One supplied file and its selected deterministic extractor, if any."""

    file_id: str
    filename: str
    path: pathlib.Path
    extractor_name: str | None = None


@dataclasses.dataclass
class ResidentDataDependencies:
    """Files and cached extractions available during one agent run."""

    files: dict[str, ResidentFileSource]
    extractor_service: DocumentExtractorService
    extracted_files: dict[str, ResidentExtraction] = dataclasses.field(
        default_factory=dict,
    )
    unprocessed_file_ids: set[str] = dataclasses.field(default_factory=set)


_provider = OpenAIProvider(api_key=SETTINGS.open_ai_api_key)
_model = OpenAIResponsesModel(RESIDENT_DATA_MODEL, provider=_provider)
resident_data_agent = Agent(
    _model,
    deps_type=ResidentDataDependencies,
    output_type=ResidentContext,
    instructions=RESIDENT_DATA_INSTRUCTIONS,
)


def _get_agent_source(
    ctx: RunContext[ResidentDataDependencies],
    file_id: str,
    *,
    suffix: str,
) -> ResidentFileSource:
    """Return a source explicitly made available for additional agent review."""
    try:
        source = ctx.deps.files[file_id]
    except KeyError as error:
        msg = f"Unknown file_id: {file_id}"
        raise ValueError(msg) from error
    if file_id not in ctx.deps.unprocessed_file_ids:
        msg = f"{file_id} is not available for additional review"
        raise ValueError(msg)
    if source.path.suffix.lower() != suffix:
        msg = f"{file_id} is not a {suffix} file"
        raise ValueError(msg)
    return source


@resident_data_agent.tool
def read_unprocessed_pdf(
    ctx: RunContext[ResidentDataDependencies],
    file_id: str,
) -> str:
    """Read text from a PDF made available for additional agent review."""
    source = _get_agent_source(ctx, file_id, suffix=".pdf")
    with pymupdf.open(source.path) as document:
        return "\n".join(
            text
            for page_number in range(document.page_count)
            if (text := document.load_page(page_number).get_text().strip())
        )


@resident_data_agent.tool
def read_unprocessed_csv(
    ctx: RunContext[ResidentDataDependencies],
    file_id: str,
) -> str:
    """Read text from a CSV made available for additional agent review."""
    source = _get_agent_source(ctx, file_id, suffix=".csv")
    return source.path.read_text(encoding="utf-8-sig", errors="replace")


class ResidentDataAgent:
    """Run deterministic extraction before the LLM completes resident context."""

    def __init__(
        self,
        agent: Agent[ResidentDataDependencies, ResidentContext] | None = None,
        extractor_service: DocumentExtractorService | None = None,
        resident_repo: ResidentRepo | None = None,
    ) -> None:
        """Initialize optional dependencies for production or testing."""
        self.agent = agent or resident_data_agent
        self.extractor_service = extractor_service or DocumentExtractorService()
        if resident_repo is None:
            from ntk.database.db import get_session  # noqa: PLC0415

            resident_repo = ResidentRepo(session=next(get_session()))
        self.resident_repo = resident_repo

    async def run(
        self,
        paths: list[pathlib.Path],
        context: str | None = None,
    ) -> ResidentContext:
        """Extract files, merge known facts, then review only eligible sources."""
        dependencies = self._build_dependencies(paths)
        resident_context = self.build_deterministic_context(dependencies)
        if dependencies.unprocessed_file_ids or (context and context.strip()):
            resident_context = await self._review_context(
                dependencies,
                context,
                resident_context,
            )
            resident_context.merge_extractions(
                dependencies.extracted_files.values(),
                prefer_extracted=True,
            )
        self._add_database_identity(resident_context)
        return resident_context

    async def _review_context(
        self,
        dependencies: ResidentDataDependencies,
        context: str | None,
        resident_context: ResidentContext,
    ) -> ResidentContext:
        """Let the LLM add facts from sources selected for additional review."""
        prompt = self._build_prompt(dependencies, context, resident_context)
        output = (await self.agent.run(prompt, deps=dependencies)).output
        return ResidentContext.model_validate(output)

    def extract_files(self, dependencies: ResidentDataDependencies) -> None:
        """Run each selected resident extractor once and cache its result."""
        for source in dependencies.files.values():
            if source.file_id in dependencies.extracted_files:
                continue
            if source.extractor_name is None:
                dependencies.unprocessed_file_ids.add(source.file_id)
                continue
            if source.extractor_name == "WoundReportExtractor":
                continue
            extraction = dependencies.extractor_service.extract_file(
                source.path,
                expected_extractor=source.extractor_name,
            )
            expected_type = _EXTRACTION_TYPE_BY_EXTRACTOR[source.extractor_name]
            if not isinstance(extraction, expected_type):
                msg = (
                    f"{source.extractor_name} returned {type(extraction).__name__}; "
                    f"expected {expected_type.__name__}"
                )
                raise TypeError(msg)
            dependencies.extracted_files[source.file_id] = extraction
            # Progress notes contain narrative clinical details that the structured
            # extractor intentionally does not infer, so the LLM may inspect them too.
            if isinstance(extraction, PccProgressNotesExtraction):
                dependencies.unprocessed_file_ids.add(source.file_id)
        facility_id = next(
            (
                extraction.facility_id
                for extraction in dependencies.extracted_files.values()
                if extraction.facility_id
            ),
            None,
        )
        for source in dependencies.files.values():
            if (
                source.extractor_name != "WoundReportExtractor"
                or source.file_id in dependencies.extracted_files
            ):
                continue
            extraction = dependencies.extractor_service.extract_file(
                source.path,
                expected_extractor=source.extractor_name,
                resident_facility_id=facility_id,
            )
            if not isinstance(extraction, CsvWoundReportExtraction):
                msg = (
                    f"{source.extractor_name} returned {type(extraction).__name__}; "
                    f"expected {CsvWoundReportExtraction.__name__}"
                )
                raise TypeError(msg)
            dependencies.extracted_files[source.file_id] = extraction

    def build_deterministic_context(
        self,
        dependencies: ResidentDataDependencies,
    ) -> ResidentContext:
        """Build context by merging every cached deterministic extraction."""
        self.extract_files(dependencies)
        resident_context = ResidentContext()
        resident_context.merge_extractions(dependencies.extracted_files.values())
        return resident_context

    def _add_database_identity(self, resident_context: ResidentContext) -> None:
        """Attach the database resident id when the extracted facility id exists."""
        if resident_context.facility_id is None:
            return
        resident = self.resident_repo.get_by_facility_id(resident_context.facility_id)
        if resident is not None:
            resident_context.resident_id = str(resident.id)

    def _build_dependencies(
        self,
        paths: list[pathlib.Path],
    ) -> ResidentDataDependencies:
        if not paths:
            msg = "At least one PDF or CSV file is required"
            raise ValueError(msg)

        sources: dict[str, ResidentFileSource] = {}
        for index, path in enumerate(paths, start=1):
            self._validate_file(path)
            extractor = self.extractor_service.get_extractor(path)
            extractor_name = self._resident_extractor_name(extractor)
            file_id = f"file_{index}"
            sources[file_id] = ResidentFileSource(
                file_id=file_id,
                filename=path.name,
                path=path,
                extractor_name=extractor_name,
            )
        return ResidentDataDependencies(
            files=sources,
            extractor_service=self.extractor_service,
        )

    @staticmethod
    def _resident_extractor_name(extractor: BaseExtractor | None) -> str | None:
        if extractor is None:
            return None
        extractor_name = type(extractor).__name__
        if extractor_name in _EXTRACTION_TYPE_BY_EXTRACTOR:
            return extractor_name
        return None

    @staticmethod
    def _build_prompt(
        dependencies: ResidentDataDependencies,
        context: str | None,
        deterministic_context: ResidentContext,
    ) -> str:
        review_sources = [
            dependencies.files[file_id]
            for file_id in sorted(dependencies.unprocessed_file_ids)
        ]
        manifest = "\n".join(
            f"- {source.file_id}: filename={source.filename!r}; "
            f"type={source.path.suffix.lower()}"
            for source in review_sources
        )
        payload = json.dumps(deterministic_context.clinical_payload(), indent=2)
        sections = [
            RESIDENT_DATA_INSTRUCTIONS,
            "Current ResidentContext populated by deterministic extractors:\n"
            + payload,
            "Files available for additional review:\n" + (manifest or "None"),
            (
                "Use read_unprocessed_pdf for .pdf files and read_unprocessed_csv "
                "for .csv files. Only call tools for file_ids listed above."
            ),
        ]
        if context and context.strip():
            sections.append(
                "Supplementary user context (not file-derived):\n" + context.strip(),
            )
        return "\n\n".join(sections)

    @staticmethod
    def _validate_file(path: pathlib.Path) -> None:
        if not path.is_file():
            msg = f"Resident data file does not exist: {path}"
            raise ValueError(msg)
        if path.suffix.lower() not in _SUPPORTED_SUFFIXES:
            msg = f"Path is not a PDF or CSV file: {path}"
            raise ValueError(msg)
        if path.stat().st_size == 0:
            msg = f"Resident data file is empty: {path}"
            raise ValueError(msg)
