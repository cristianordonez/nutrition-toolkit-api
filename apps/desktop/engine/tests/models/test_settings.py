from __future__ import annotations

import typing

from engine.models.settings import Settings
from ntk.utils.parallel import PoolMode

if typing.TYPE_CHECKING:
    import pytest


def test_document_ingestion_pool_defaults() -> None:
    settings = Settings()

    assert settings.document_ingestion_pool_mode is PoolMode.THREAD
    assert settings.document_ingestion_workers == 3  # noqa: PLR2004
    assert settings.clinical_note_extraction_concurrency == 8  # noqa: PLR2004


def test_clinical_note_extraction_concurrency_is_configurable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NTK_CLINICAL_NOTE_EXTRACTION_CONCURRENCY", "5")

    assert Settings().clinical_note_extraction_concurrency == 5  # noqa: PLR2004
