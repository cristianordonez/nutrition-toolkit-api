from __future__ import annotations

import asyncio
import pathlib

from ntk.controllers.resident.app import ResidentControllerGroup
from ntk.controllers.resident.extract import (
    ResidentExtractController,
    ResidentExtractOptions,
)
from ntk.models.sql.resident import ResidentContext


class Agent:
    async def run(
        self,
        files: list[pathlib.Path],
        context: str | None,
    ) -> ResidentContext:
        assert files == [pathlib.Path("resident.pdf")]
        assert context == "dialysis"
        return ResidentContext()


def test_resident_group_and_extract_controller() -> None:
    group = ResidentControllerGroup()
    assert len(group.subcommands) == 1
    assert isinstance(group.subcommands[0], ResidentExtractController)

    controller = ResidentExtractController(agent=Agent())  # ty: ignore[invalid-argument-type]
    output = asyncio.run(
        controller.run(
            ResidentExtractOptions(
                files=[pathlib.Path("resident.pdf")],
                context="dialysis",
            ),
        ),
    )
    assert output.controller == "extract"
    assert output.result.age is None
