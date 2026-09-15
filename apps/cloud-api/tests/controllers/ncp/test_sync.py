from __future__ import annotations

import asyncio

import pytest

from api.controllers.ncp import sync
from api.controllers.ncp.sync import NCPSyncController


def test_sync_controller_reports_deferred_promotion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """NCP import/promotion is deferred; see the split refactor plan decision 7."""

    class Repository:
        def __init__(self, session: object) -> None:
            assert session == "session"

    monkeypatch.setattr(sync, "NCPRepo", Repository)

    with pytest.raises(NotImplementedError, match="deferred"):
        asyncio.run(
            NCPSyncController(
                session="session",  # ty: ignore[invalid-argument-type]
            ).run(sync.NCPSyncOptions()),
        )
