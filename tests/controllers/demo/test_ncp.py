from __future__ import annotations

import asyncio
import contextlib
import typing
from types import SimpleNamespace

from ntk.controllers.demo import ncp
from ntk.controllers.demo.ncp import (
    DemoNCPController,
    DemoNCPOptions,
)

if typing.TYPE_CHECKING:
    from collections.abc import Iterator

    import pytest


def test_demo_controller_passes_all_uploads_to_shared_pipeline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    files = [object(), object()]
    expected = object()

    @contextlib.contextmanager
    def session_scope(session: object) -> Iterator[object]:
        assert session == "session"
        yield session

    class Pipeline:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        @staticmethod
        async def run_uploads(uploads: object) -> object:
            assert uploads == files
            return expected

    patch = monkeypatch.setattr
    patch(ncp, "controller_session", session_scope)
    patch(ncp, "DemoNutritionCareProcessPipeline", Pipeline)
    for name in (
        "EmbeddingRepo",
        "EmbeddingService",
        "FoodRepo",
        "PersonDetailBuilder",
        "TubeFeedCalculator",
    ):
        patch(ncp, name, lambda *_args, **_kwargs: object())
    patch(ncp, "Output", SimpleNamespace)

    output = asyncio.run(
        DemoNCPController("session").run(DemoNCPOptions(files=files)),  # ty: ignore[invalid-argument-type]
    )

    assert output.result is expected
    assert output.controller == "demo-ncp"
    assert output.exit_code == 0
