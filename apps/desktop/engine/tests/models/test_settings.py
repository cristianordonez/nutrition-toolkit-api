from __future__ import annotations

import typing

from engine.models.settings import Settings

if typing.TYPE_CHECKING:
    import pytest


def test_document_extraction_concurrency_default() -> None:
    settings = Settings()

    assert settings.clinical_note_extraction_concurrency == 8  # noqa: PLR2004


def test_clinical_note_extraction_concurrency_is_configurable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NTK_CLINICAL_NOTE_EXTRACTION_CONCURRENCY", "5")

    assert Settings().clinical_note_extraction_concurrency == 5  # noqa: PLR2004
