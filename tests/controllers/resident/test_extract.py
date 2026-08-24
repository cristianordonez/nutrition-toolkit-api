from __future__ import annotations

import asyncio
import pathlib

from ntk.controllers.resident.app import ResidentControllerGroup
from ntk.controllers.resident.extract import (
    ResidentExtractController,
    ResidentExtractOptions,
)
from ntk.models.resident_data import ResidentContext
from ntk.models.sql.resident import ResidentSnapshot


class Agent:
    async def extract(
        self,
        files: list[pathlib.Path],
        context: str | None,
    ) -> ResidentContext:
        assert files == [pathlib.Path("resident.pdf")]
        assert context == "dialysis"
        return ResidentContext(resident_snapshot=ResidentSnapshot())


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
    assert output.result.resident_snapshot.age is None
