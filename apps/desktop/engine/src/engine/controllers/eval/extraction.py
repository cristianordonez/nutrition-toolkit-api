"""Run the same documents through each model and compare the results.

This exists to answer one question before committing to on-device extraction:
can a local model actually hold the extraction schema? It runs the real
``UnknownFileExtractor.extract`` path per provider, so what it measures is the
production code path with only the model swapped.

Nothing is persisted. Running full ingestion twice would be misleading anyway,
because the second run would dedupe against the first on document checksum and
fact key.
"""

# Pydantic resolves these annotation types at runtime when building schemas.
# ruff: noqa: TC003

from __future__ import annotations

import collections
import pathlib
import time
import typing

from pydantic import BaseModel, Field

from engine.agents.data_extraction_agent import (
    DataExtractionAgent,
    build_unknown_document_agent,
)
from engine.clients.ollama_client import OllamaClient
from engine.models.settings import SETTINGS
from engine.pipelines.person.ingestion.extract.unknown_file import UnknownFileExtractor
from engine.services.local_model import resolve_model
from ntk.controllers.base import BaseController
from ntk.models.base import ConsoleRenderableModel
from ntk.models.output import Output

if typing.TYPE_CHECKING:
    from engine.agents.data_extraction_agent import ExtractionProvider
    from engine.models.extracted_fact_create import ExtractedFactCreate

_PROVIDERS: tuple[str, ...] = ("openai", "ollama")


class EvalExtractionOptions(BaseModel):
    """Documents to run through each provider."""

    files: list[pathlib.Path] = Field(min_length=1)
    # A plain default, not default_factory: the CLI marks a field required when
    # its default is PydanticUndefined, which a factory leaves unset.
    providers: list[str] = Field(default=list(_PROVIDERS))


class _CountingAgent:
    """Wrap an agent to count the chunk failures the extractor swallows.

    ``UnknownFileExtractor`` logs and skips a chunk whose model call raises, so
    a provider that is timing out or refusing connections would otherwise show
    up here as a model that simply found nothing. Wrapping the agent catches
    each failure before the extractor buries it, then re-raises so extraction
    behaves exactly as it does in production.
    """

    def __init__(self, inner: typing.Any) -> None:  # noqa: ANN401
        self._inner = inner
        self.calls = 0
        self.failures = 0

    @property
    def model(self) -> typing.Any:  # noqa: ANN401
        """Expose the wrapped agent's model so the report can name it."""
        return self._inner.model

    async def run(self, *args: typing.Any, **kwargs: typing.Any) -> typing.Any:  # noqa: ANN401
        """Run the wrapped agent, counting calls and failures."""
        self.calls += 1
        try:
            return await self._inner.run(*args, **kwargs)
        except Exception:
            self.failures += 1
            raise


class DocumentOutcome(BaseModel):
    """One document's result for one provider."""

    document: str
    seconds: float
    facts: int
    error: str | None = None


class ProviderRun(BaseModel):
    """Everything one provider produced across the documents."""

    provider: str
    model: str
    total_seconds: float
    total_facts: int
    chunks: int = 0
    chunk_failures: int = 0
    fact_types: dict[str, int]
    documents: list[DocumentOutcome]
    error: str | None = None


class EvalExtractionResult(ConsoleRenderableModel):
    """Side-by-side comparison of every provider that ran."""

    runs: list[ProviderRun]

    def to_console(self) -> str:
        """Render a comparison table, then the per-document detail as JSON."""
        header = f"{'provider':10} {'model':22} {'seconds':>9} {'facts':>7}"
        lines = [header, "-" * len(header)]
        for run in self.runs:
            lines.append(
                f"{run.provider:10} {run.model[:22]:22} "
                f"{run.total_seconds:9.1f} {run.total_facts:7}",
            )
            if run.error:
                lines.append(f"{'':10} error: {run.error}")
            if run.chunk_failures:
                lines.append(
                    f"{'':10} WARNING: {run.chunk_failures}/{run.chunks} model "
                    "calls failed; counts below are not a fair comparison",
                )
        lines.append("")
        lines.append(self.model_dump_json(indent=2))
        return "\n".join(lines)


class EvalExtractionController(BaseController):
    """Compare extraction speed and yield across providers."""

    name = "extraction"
    help = "Run documents through each model and compare time and fact counts"
    options_model = EvalExtractionOptions

    async def run(
        self,
        options: EvalExtractionOptions,
    ) -> Output[EvalExtractionResult]:
        """Run every provider over every document and collect the numbers."""
        runs = [
            await self._run_provider(
                typing.cast("ExtractionProvider", provider),
                options.files,
            )
            for provider in options.providers
        ]
        return Output(
            result=EvalExtractionResult(runs=runs),
            controller=self.name,
            exit_code=0,
        )

    @staticmethod
    async def _preflight(provider: ExtractionProvider) -> str | None:
        """Return why this provider cannot run, or None when it can.

        Worth checking up front because the extractor swallows per-chunk
        failures, so a provider that is simply switched off would otherwise
        report zero facts and read as a bad model rather than a missing one.
        """
        if provider == "ollama":
            client = OllamaClient(SETTINGS.ollama_host)
            if not await client.is_available():
                return f"Ollama is not running at {SETTINGS.ollama_host}."
            model = resolve_model(override=SETTINGS.ollama_model)
            if not await client.has_model(model):
                return f"{model} is not downloaded. Run: engine localmodel ensure"
            return None
        if not SETTINGS.open_ai_api_key:
            return "NTK_OPEN_AI_API_KEY is not set."
        return None

    async def _run_provider(
        self,
        provider: ExtractionProvider,
        files: list[pathlib.Path],
    ) -> ProviderRun:
        """Run one provider over every document."""
        if blocked := await self._preflight(provider):
            return ProviderRun(
                provider=provider,
                model="unavailable",
                total_seconds=0.0,
                total_facts=0,
                fact_types={},
                documents=[],
                error=blocked,
            )
        try:
            agent = _CountingAgent(build_unknown_document_agent(provider))
            model_name = str(agent.model.model_name)
        except Exception as error:  # noqa: BLE001 - report, do not abort the comparison
            return ProviderRun(
                provider=provider,
                model="unavailable",
                total_seconds=0.0,
                total_facts=0,
                fact_types={},
                documents=[],
                error=str(error),
            )

        outcomes: list[DocumentOutcome] = []
        fact_types: collections.Counter[str] = collections.Counter()
        for file in files:
            outcome, facts = await self._run_document(file, agent)
            outcomes.append(outcome)
            fact_types.update(fact.payload.type for fact in facts)

        return ProviderRun(
            provider=provider,
            model=model_name,
            total_seconds=round(sum(o.seconds for o in outcomes), 2),
            total_facts=sum(o.facts for o in outcomes),
            chunks=agent.calls,
            chunk_failures=agent.failures,
            fact_types=dict(sorted(fact_types.items())),
            documents=outcomes,
        )

    @staticmethod
    async def _run_document(
        file: pathlib.Path,
        agent: object,
    ) -> tuple[DocumentOutcome, list[ExtractedFactCreate]]:
        """Time one document through the real extraction path.

        Construction is inside the timed block because an unreadable or
        unsupported file raises there, and one bad document should be reported
        rather than ending the comparison.
        """
        started = time.perf_counter()
        try:
            extractor = UnknownFileExtractor(
                file,
                extraction_agent=DataExtractionAgent(
                    unknown_document_agent=agent,  # ty: ignore[invalid-argument-type]
                ),
            )
            facts = await extractor.extract()
        except Exception as error:  # noqa: BLE001 - one bad document must not stop the run
            return (
                DocumentOutcome(
                    document=file.name,
                    seconds=round(time.perf_counter() - started, 2),
                    facts=0,
                    error=str(error),
                ),
                [],
            )
        return (
            DocumentOutcome(
                document=file.name,
                seconds=round(time.perf_counter() - started, 2),
                facts=len(facts),
            ),
            facts,
        )


__all__ = [
    "EvalExtractionController",
    "EvalExtractionOptions",
    "EvalExtractionResult",
]
