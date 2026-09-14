"""Import ncps from a clinical-note report."""

from __future__ import annotations

import pathlib
import typing

from pydantic import BaseModel, Field

from ntk.controllers.base import BaseController
from ntk.controllers.session import controller_session
from ntk.models.base import ConsoleRenderableModel
from ntk.models.output import Output
from ntk.models.sql.person import (
    PersonClinicalNote,  # noqa: TC001 - Pydantic runtime
)
from ntk.pipelines.ncp.ingest.import_pipeline import (
    InvalidClinicalNoteReportError,
    NCPImportPipeline,
)

if typing.TYPE_CHECKING:
    from sqlmodel import Session

    from ntk.controllers.uploads import ReadableUpload


class NCPImportOptions(BaseModel):
    """Clinical-note report containing Nutrition Care Processes."""

    path: pathlib.Path = Field(description="PCC clinical-note report PDF")
    overwrite: bool = False
    created_by: str | None = None


class NCPImportFailure(BaseModel):
    """One uploaded file rejected without stopping the remaining imports."""

    filename: str
    detail: str


class NCPImportResult(ConsoleRenderableModel):
    """Nutrition ncps imported from one or more clinical-note reports."""

    ncps: list[PersonClinicalNote]
    failures: list[NCPImportFailure] = Field(default_factory=list)

    def to_console(self) -> str:
        """Render imported ncp IDs and rejected input files."""
        lines = [str(ncp.id) for ncp in self.ncps]
        lines.extend(
            f"FAILED {failure.filename}: {failure.detail}" for failure in self.failures
        )
        return "\n".join(lines)


class NCPImportController(BaseController):
    """Import nutrition notes as finalized Nutrition Care Processes."""

    name = "import"
    help = "Import Nutrition Care Processes from a PCC clinical-note report"
    options_model = NCPImportOptions

    def __init__(self, session: Session | None = None) -> None:
        """Store the optional controller-owned session."""
        self.session = session

    async def run_upload(
        self,
        file: ReadableUpload,
        *,
        overwrite: bool = False,
        created_by: str | None = None,
    ) -> Output[NCPImportResult]:
        """Delegate one uploaded clinical-note report to the import workflow."""
        with controller_session(self.session) as session:
            ncps = await NCPImportPipeline.from_session(
                session,
            ).run_upload(
                file,
                overwrite=overwrite,
                created_by=created_by,
            )
        return self._output(ncps)

    async def run_uploads(
        self,
        files: typing.Sequence[ReadableUpload],
        *,
        overwrite: bool = False,
        created_by: str | None = None,
    ) -> Output[NCPImportResult]:
        """Import every valid report and retain failures for invalid reports."""
        if not files:
            message = "At least one PCC clinical-note report PDF is required"
            raise ValueError(message)
        ncps: list[PersonClinicalNote] = []
        failures: list[NCPImportFailure] = []
        with controller_session(self.session) as session:
            pipeline = NCPImportPipeline.from_session(session)
            for index, file in enumerate(files):
                filename = pathlib.Path(
                    file.filename or f"clinical-notes-{index + 1}.pdf",
                ).name
                try:
                    ncps.extend(
                        await pipeline.run_upload(
                            file,
                            overwrite=overwrite,
                            created_by=created_by,
                        ),
                    )
                except InvalidClinicalNoteReportError as error:
                    failures.append(
                        NCPImportFailure(
                            filename=filename,
                            detail=str(error),
                        ),
                    )
        return self._output(ncps, failures=failures)

    async def run(
        self,
        options: NCPImportOptions,
    ) -> Output[NCPImportResult]:
        """Delegate one local clinical-note report to the import workflow."""
        with controller_session(self.session) as session:
            ncps = await NCPImportPipeline.from_session(session).run(
                options.path,
            )
        return self._output(ncps)

    @classmethod
    def _output(
        cls,
        ncps: list[PersonClinicalNote],
        *,
        failures: list[NCPImportFailure] | None = None,
    ) -> Output[NCPImportResult]:
        """Build the shared CLI controller result."""
        return Output(
            result=NCPImportResult(
                ncps=ncps,
                failures=failures or [],
            ),
            controller=cls.name,
            exit_code=0,
        )


__all__ = [
    "NCPImportController",
    "NCPImportFailure",
    "NCPImportOptions",
    "NCPImportResult",
]
