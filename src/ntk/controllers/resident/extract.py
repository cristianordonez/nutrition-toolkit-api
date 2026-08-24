"""Extract structured resident data from PDF and CSV files."""

from __future__ import annotations

import pathlib  # noqa: TC003
import typing

from pydantic import BaseModel, Field

from ntk.agents.resident_data_agent import ResidentDataAgent
from ntk.controllers.base import BaseController
from ntk.controllers.uploads import (
    ReadableUpload,
    UploadRequirements,
    materialize_uploads,
)
from ntk.models.output import Output

if typing.TYPE_CHECKING:
    from ntk.models.resident_data import ResidentContext


class ResidentExtractOptions(BaseModel):
    """Options for resident data extraction."""

    files: list[pathlib.Path] = Field(
        description="One or more resident PDF or CSV files",
    )
    context: str | None = Field(
        default=None,
        description="Optional facts or extraction guidance supplied by the user",
    )


class ResidentExtractController(BaseController):
    """Extract a combined resident record from PDF and CSV files."""

    name = "extract"
    help = "Extract structured resident data from PDF or CSV files"
    options_model = ResidentExtractOptions

    def __init__(self, agent: ResidentDataAgent | None = None) -> None:
        """Initialize with an optional extraction agent."""
        self.agent = agent

    async def run_uploads(
        self,
        files: typing.Sequence[ReadableUpload],
        context: str | None = None,
    ) -> Output[ResidentContext]:
        """Validate uploaded resident files and extract resident data."""
        async with materialize_uploads(
            files,
            UploadRequirements(
                allowed_suffixes=frozenset({".csv", ".pdf"}),
                file_description="PDF or CSV file",
                directory_prefix="ntk-resident-",
                default_filename=lambda index: f"resident-{index + 1}.pdf",
                reject_empty=True,
            ),
        ) as uploads:
            return await self.run(
                ResidentExtractOptions(files=uploads.paths, context=context),
            )

    async def run(self, options: ResidentExtractOptions) -> Output[ResidentContext]:
        """Run resident data extraction."""
        agent = self.agent or ResidentDataAgent()
        resident_data = await agent.extract(options.files, options.context)
        return Output(result=resident_data, controller=self.name, exit_code=0)
