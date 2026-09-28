"""Validate build assets and exercise real inference without cache or network."""

from __future__ import annotations

import hashlib
import json
import pathlib
import runpy
import subprocess
import sys

import pytest

from engine import paths

_ENGINE_ROOT = pathlib.Path(__file__).resolve().parents[1]


def _validate(directory: pathlib.Path, files: dict[str, str]) -> None:
    helpers = runpy.run_path(str(_ENGINE_ROOT / "scripts/prepare_embedding_model.py"))
    helpers["validate_bundle"](directory, files)


def test_asset_validation_rejects_missing_and_modified_files(
    tmp_path: pathlib.Path,
) -> None:
    files = {"weights": hashlib.sha256(b"pinned weights").hexdigest()}
    with pytest.raises(RuntimeError, match="Missing bundled model file"):
        _validate(tmp_path, files)
    (tmp_path / "weights").write_bytes(b"different weights")
    with pytest.raises(RuntimeError, match="checksum mismatch"):
        _validate(tmp_path, files)
    (tmp_path / "weights").write_bytes(b"pinned weights")
    _validate(tmp_path, files)


def test_preparation_copies_snapshot_without_cache_symlinks(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "snapshot"
    source.mkdir()
    (source / "weights").write_bytes(b"pinned weights")
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "minilm.json").write_text(
        json.dumps(
            {
                "directory": "model",
                "files": {"weights": hashlib.sha256(b"pinned weights").hexdigest()},
            },
        ),
    )
    helpers = runpy.run_path(str(_ENGINE_ROOT / "scripts/prepare_embedding_model.py"))
    prepare = helpers["prepare"]
    monkeypatch.setitem(prepare.__globals__, "_ASSETS", assets)
    destination = prepare(source)
    assert (destination / "weights").read_bytes() == b"pinned weights"
    assert not (destination / "weights").is_symlink()


def test_real_bundled_model_never_attempts_network(tmp_path: pathlib.Path) -> None:
    try:
        paths.bundled_embedding_model_dir()
    except FileNotFoundError:
        pytest.skip("Prepare MiniLM assets to run the real offline integration test")
    result = subprocess.run(  # noqa: S603 - fixed local verification script
        [sys.executable, str(_ENGINE_ROOT / "scripts/verify_offline_embeddings.py")],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout.splitlines()[-1])
    assert report["network_attempts"] == []
    assert report["shared_model"]


def test_manifest_model_identity_has_not_changed() -> None:
    from engine.database.vectors import EMBEDDING_MODEL  # noqa: PLC0415

    manifest = json.loads(
        (_ENGINE_ROOT / "src/engine/assets/models/minilm.json").read_text(),
    )
    assert f"sentence-transformers:{manifest['repo_id']}" == EMBEDDING_MODEL
