"""Ingest deidentified NCP notes from clinical-note reports as examples."""

from __future__ import annotations

import pathlib
import typing

from pydantic import BaseModel, Field

from engine.controllers.base import BaseController
from engine.database.sessions import controller_session
from engine.models.base import ConsoleRenderableModel
from engine.models.output import Output
from engine.pipelines.ncp.ingest.ingest_pipeline import (
    InvalidClinicalNoteReportError,
    NCPIngestPipeline,
    NCPIngestSummary,
)

if typing.TYPE_CHECKING:
    from sqlmodel import Session

    from engine.controllers.uploads import ReadableUpload


class NCPIngestOptions(BaseModel):
    """Clinical-note report containing Nutrition Care Processes."""

    path: pathlib.Path = Field(description="PCC clinical-note report PDF")


class NCPIngestFailure(BaseModel):
    """One uploaded file rejected without stopping the remaining reports."""

    filename: str
    detail: str


class NCPIngestResult(ConsoleRenderableModel):
    """Summary of the NCP examples ingested from one or more reports."""

    reports_ingested: int
    notes_ingested: int
    duplicates_skipped: int
    pointer_notes_skipped: int = 0
    failures: list[NCPIngestFailure] = Field(default_factory=list)

    def to_console(self) -> str:
        """Render the ingested note counts and rejected input files."""
        lines = [
            (
                f"Ingested {self.notes_ingested} NCP example(s) from "
                f"{self.reports_ingested} report(s); skipped "
                f"{self.duplicates_skipped} duplicate(s) and "
                f"{self.pointer_notes_skipped} pointer note(s)."
            ),
        ]
        lines.extend(
            f"FAILED {failure.filename}: {failure.detail}" for failure in self.failures
        )
        return "\n".join(lines)


class NCPIngestController(BaseController):
    """Ingest deidentified NCP notes from a PCC report as style examples."""

    name = "ingest"
    help = "Ingest deidentified NCP notes from a PCC clinical-note report as examples"
    options_model = NCPIngestOptions

    def __init__(self, session: Session | None = None) -> None:
        """Store the optional controller-owned session."""
        self.session = session

    async def run_upload(
        self,
        file: ReadableUpload,
    ) -> Output[NCPIngestResult]:
        """Delegate one uploaded clinical-note report to the ingest workflow."""
        with controller_session(self.session) as session:
            summary = await NCPIngestPipeline.from_session(
                session,
            ).run_upload(file)
        return self._output([summary])

    async def run_uploads(
        self,
        files: typing.Sequence[ReadableUpload],
    ) -> Output[NCPIngestResult]:
        """Ingest every valid report and retain failures for invalid reports."""
        if not files:
            message = "At least one PCC clinical-note report PDF is required"
            raise ValueError(message)
        summaries: list[NCPIngestSummary] = []
        failures: list[NCPIngestFailure] = []
        with controller_session(self.session) as session:
            pipeline = NCPIngestPipeline.from_session(session)
            for index, file in enumerate(files):
                filename = pathlib.Path(
                    file.filename or f"clinical-notes-{index + 1}.pdf",
                ).name
                try:
                    summaries.append(await pipeline.run_upload(file))
                except InvalidClinicalNoteReportError as error:
                    failures.append(
                        NCPIngestFailure(
                            filename=filename,
                            detail=str(error),
                        ),
                    )
        return self._output(summaries, failures=failures)

    async def run(
        self,
        options: NCPIngestOptions,
    ) -> Output[NCPIngestResult]:
        """Delegate one local clinical-note report to the ingest workflow."""
        with controller_session(self.session) as session:
            summary = await NCPIngestPipeline.from_session(session).run(
                options.path,
            )
        return self._output([summary])

    @classmethod
    def _output(
        cls,
        summaries: list[NCPIngestSummary],
        *,
        failures: list[NCPIngestFailure] | None = None,
    ) -> Output[NCPIngestResult]:
        """Build the shared CLI controller result."""
        return Output(
            result=NCPIngestResult(
                reports_ingested=len(summaries),
                notes_ingested=sum(s.notes_ingested for s in summaries),
                duplicates_skipped=sum(s.duplicates_skipped for s in summaries),
                pointer_notes_skipped=sum(s.pointer_notes_skipped for s in summaries),
                failures=failures or [],
            ),
            controller=cls.name,
            exit_code=0,
        )


__all__ = [
    "NCPIngestController",
    "NCPIngestFailure",
    "NCPIngestOptions",
    "NCPIngestResult",
]
