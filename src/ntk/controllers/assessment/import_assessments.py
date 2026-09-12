"""Import assessments from a progress-note report."""

from __future__ import annotations

import pathlib
import typing

from pydantic import BaseModel, Field

from ntk.controllers.base import BaseController
from ntk.controllers.session import controller_session
from ntk.models.base import ConsoleRenderableModel
from ntk.models.output import Output
from ntk.models.sql.person import PersonAssessment  # noqa: TC001 - Pydantic runtime
from ntk.pipelines.assessment.ingest.import_pipeline import (
    AssessmentImportPipeline,
    InvalidProgressNoteReportError,
)

if typing.TYPE_CHECKING:
    from sqlmodel import Session

    from ntk.controllers.uploads import ReadableUpload


class AssessmentImportOptions(BaseModel):
    """Progress-note report containing nutrition assessments."""

    path: pathlib.Path = Field(description="PCC progress-note report PDF")
    overwrite: bool = False
    created_by: str | None = None


class AssessmentImportFailure(BaseModel):
    """One uploaded file rejected without stopping the remaining imports."""

    filename: str
    detail: str


class AssessmentImportResult(ConsoleRenderableModel):
    """Nutrition assessments imported from one or more progress-note reports."""

    assessments: list[PersonAssessment]
    failures: list[AssessmentImportFailure] = Field(default_factory=list)

    def to_console(self) -> str:
        """Render imported assessment IDs and rejected input files."""
        lines = [str(assessment.id) for assessment in self.assessments]
        lines.extend(
            f"FAILED {failure.filename}: {failure.detail}" for failure in self.failures
        )
        return "\n".join(lines)


class AssessmentImportController(BaseController):
    """Import nutrition notes as finalized person assessments."""

    name = "import"
    help = "Import nutrition assessments from a PCC progress-note report"
    options_model = AssessmentImportOptions

    def __init__(self, session: Session | None = None) -> None:
        """Store the optional controller-owned session."""
        self.session = session

    async def run_upload(
        self,
        file: ReadableUpload,
        *,
        overwrite: bool = False,
        created_by: str | None = None,
    ) -> Output[AssessmentImportResult]:
        """Delegate one uploaded progress-note report to the import workflow."""
        with controller_session(self.session) as session:
            assessments = await AssessmentImportPipeline.from_session(
                session,
            ).run_upload(
                file,
                overwrite=overwrite,
                created_by=created_by,
            )
        return self._output(assessments)

    async def run_uploads(
        self,
        files: typing.Sequence[ReadableUpload],
        *,
        overwrite: bool = False,
        created_by: str | None = None,
    ) -> Output[AssessmentImportResult]:
        """Import every valid report and retain failures for invalid reports."""
        if not files:
            message = "At least one PCC progress-note report PDF is required"
            raise ValueError(message)
        assessments: list[PersonAssessment] = []
        failures: list[AssessmentImportFailure] = []
        with controller_session(self.session) as session:
            pipeline = AssessmentImportPipeline.from_session(session)
            for index, file in enumerate(files):
                filename = pathlib.Path(
                    file.filename or f"progress-notes-{index + 1}.pdf",
                ).name
                try:
                    assessments.extend(
                        await pipeline.run_upload(
                            file,
                            overwrite=overwrite,
                            created_by=created_by,
                        ),
                    )
                except InvalidProgressNoteReportError as error:
                    failures.append(
                        AssessmentImportFailure(
                            filename=filename,
                            detail=str(error),
                        ),
                    )
        return self._output(assessments, failures=failures)

    async def run(
        self,
        options: AssessmentImportOptions,
    ) -> Output[AssessmentImportResult]:
        """Delegate one local progress-note report to the import workflow."""
        with controller_session(self.session) as session:
            assessments = await AssessmentImportPipeline.from_session(session).run(
                options.path,
            )
        return self._output(assessments)

    @classmethod
    def _output(
        cls,
        assessments: list[PersonAssessment],
        *,
        failures: list[AssessmentImportFailure] | None = None,
    ) -> Output[AssessmentImportResult]:
        """Build the shared CLI controller result."""
        return Output(
            result=AssessmentImportResult(
                assessments=assessments,
                failures=failures or [],
            ),
            controller=cls.name,
            exit_code=0,
        )


__all__ = [
    "AssessmentImportController",
    "AssessmentImportFailure",
    "AssessmentImportOptions",
    "AssessmentImportResult",
]
