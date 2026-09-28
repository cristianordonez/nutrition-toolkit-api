"""Package-local paths and a single, strictly offline inference model."""

from __future__ import annotations

import asyncio
import json
import sys
import types
import typing
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock

import numpy as np
import pytest
from sqlmodel import Session

from engine import paths
from engine.database.vectors import EMBEDDING_DIMENSIONS, EMBEDDING_MODEL
from engine.services import embedding_service as embeddings

if typing.TYPE_CHECKING:
    import pathlib


@pytest.fixture
def constructor(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> Mock:
    model = Mock()
    model.get_embedding_dimension.return_value = EMBEDDING_DIMENSIONS
    model.encode_document.return_value = np.ones((1, EMBEDDING_DIMENSIONS))
    model.encode_query.return_value = np.ones((1, EMBEDDING_DIMENSIONS))
    constructor = Mock(return_value=model)
    module = types.ModuleType("sentence_transformers")
    vars(module)["SentenceTransformer"] = constructor
    monkeypatch.setitem(sys.modules, "sentence_transformers", module)
    monkeypatch.setattr(embeddings, "_SHARED_MODEL", None)
    monkeypatch.setattr(embeddings, "bundled_embedding_model_dir", lambda: tmp_path)
    return constructor


@pytest.mark.parametrize(
    "location",
    ["checkout/src/engine", "site-packages/engine", "app/_internal/engine"],
)
def test_model_path_is_package_relative(
    location: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
) -> None:
    package = tmp_path / location
    assets = package / "assets/models"
    model = assets / "all-MiniLM-L6-v2"
    model.mkdir(parents=True)
    (assets / "minilm.json").write_text(
        json.dumps(
            {
                "directory": model.name,
                "files": {"model.safetensors": "unused"},
            },
        ),
    )
    (model / "model.safetensors").write_bytes(b"weights")
    monkeypatch.setattr(paths, "__file__", str(package / "paths.py"))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HF_HOME", str(tmp_path / "unused-cache"))

    assert paths.bundled_embedding_model_dir() == model

    (model / "model.safetensors").write_bytes(b"")
    with pytest.raises(FileNotFoundError, match="Runtime downloads are disabled"):
        paths.bundled_embedding_model_dir()
    (model / "model.safetensors").unlink()
    with pytest.raises(FileNotFoundError, match="prepare_embedding_model"):
        paths.bundled_embedding_model_dir()


def test_missing_manifest_is_actionable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
) -> None:
    monkeypatch.setattr(paths, "__file__", str(tmp_path / "paths.py"))
    with pytest.raises(FileNotFoundError, match="manifest is missing"):
        paths.bundled_embedding_model_dir()


def test_model_load_is_lazy_offline_and_shared(
    constructor: Mock,
    tmp_path: pathlib.Path,
) -> None:
    with Session() as session:
        first = embeddings.EmbeddingService(session)
        second = embeddings.EmbeddingService(session)
        assert first.get_embeddings([]) == []
        constructor.assert_not_called()

        assert len(first.get_embedding("document")) == EMBEDDING_DIMENSIONS
        second._embed_query("query")  # noqa: SLF001
        asyncio.run(second.get_embedding_async("another document"))
        constructor.assert_called_once_with(
            str(tmp_path),
            local_files_only=True,
            trust_remote_code=False,
            token=False,
        )
        assert first.model == second.model == EMBEDDING_MODEL


def test_preserves_encoding_settings_and_truncation(constructor: Mock) -> None:
    settings = {
        "show_progress_bar": False,
        "convert_to_numpy": True,
        "convert_to_tensor": False,
        "normalize_embeddings": False,
    }
    with Session() as session:
        service = embeddings.EmbeddingService(session)
        service.get_embeddings(["  " + "a" * 9_000])
        constructor.return_value.encode_document.assert_called_once_with(
            ["  " + "a" * 7_998],
            **settings,
        )
        service._embed_query("  " + "b" * 9_000 + " ")  # noqa: SLF001
        constructor.return_value.encode_query.assert_called_once_with(
            ["b" * 8_000],
            **settings,
        )


def test_concurrent_first_calls_only_construct_one_model(constructor: Mock) -> None:
    def embed(_index: int) -> list[float]:
        with Session() as session:
            return embeddings.EmbeddingService(session).get_embedding("example")

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(embed, range(8)))
    assert all(len(row) == EMBEDDING_DIMENSIONS for row in results)
    constructor.assert_called_once()


def test_invalid_text_does_not_load_model(constructor: Mock) -> None:
    with Session() as session:
        service = embeddings.EmbeddingService(session)
        with pytest.raises(ValueError, match="must not be empty"):
            service.get_embedding(" ")
        with pytest.raises(ValueError, match="must not be empty"):
            service._embed_query(" ")  # noqa: SLF001
    constructor.assert_not_called()


def test_missing_assets_raise_application_error_before_loading(
    constructor: Mock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolver = Mock(side_effect=FileNotFoundError("Bundled MiniLM file missing"))
    monkeypatch.setattr(embeddings, "bundled_embedding_model_dir", resolver)
    with (
        Session() as session,
        pytest.raises(
            embeddings.EmbeddingUnavailableError,
            match="Bundled MiniLM file missing",
        ),
    ):
        embeddings.EmbeddingService(session).get_embedding("example")
    constructor.assert_not_called()


def test_wrong_width_is_rejected(constructor: Mock) -> None:
    constructor.return_value.get_embedding_dimension.return_value = 768
    with (
        Session() as session,
        pytest.raises(
            embeddings.EmbeddingUnavailableError,
            match="384 dimensions",
        ),
    ):
        embeddings.EmbeddingService(session).get_embedding("example")
    constructor.return_value.encode_document.assert_not_called()


def test_inference_failure_is_an_application_error(constructor: Mock) -> None:
    constructor.return_value.encode_query.side_effect = OSError("bad weights")
    with (
        Session() as session,
        pytest.raises(
            embeddings.EmbeddingUnavailableError,
            match="bad weights",
        ),
    ):
        embeddings.EmbeddingService(session)._embed_query("example")  # noqa: SLF001
