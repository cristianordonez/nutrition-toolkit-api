"""Build-time only: stage a pinned, checksum-verified MiniLM model bundle.

Use --source to copy an existing snapshot (and its LICENSE.txt) without network
access. The destination always contains real files, never cache symlinks.
"""

# ruff: noqa: INP001 - standalone build script

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import shutil
import tempfile
import urllib.request

_ASSETS = pathlib.Path(__file__).resolve().parents[1] / "src/engine/assets/models"


def validate_bundle(directory: pathlib.Path, files: dict[str, str]) -> None:
    """Fail a release build on missing, corrupt, or unpinned model assets."""
    for filename, checksum in files.items():
        path = directory / filename
        if not path.is_file() or path.is_symlink():
            msg = f"Missing bundled model file (or cache symlink): {path}"
            raise RuntimeError(msg)
        with path.open("rb") as stream:
            actual = hashlib.file_digest(stream, "sha256").hexdigest()
        if actual != checksum:
            msg = f"Bundled model checksum mismatch: {path}"
            raise RuntimeError(msg)


def prepare(source: pathlib.Path | None = None) -> pathlib.Path:
    """Download at build time, or copy a local snapshot, and validate it."""
    manifest = json.loads((_ASSETS / "minilm.json").read_text(encoding="utf-8"))
    destination = _ASSETS / manifest["directory"]
    with tempfile.TemporaryDirectory(prefix="minilm-", dir=_ASSETS) as temporary:
        staged = pathlib.Path(temporary)
        for filename in manifest["files"]:
            target = staged / filename
            target.parent.mkdir(parents=True, exist_ok=True)
            if source is not None:
                shutil.copyfile(source / filename, target)
            elif filename == "LICENSE.txt":
                # This revision declares Apache-2.0 in its model card but does
                # not contain a license file. Include the canonical text.
                with urllib.request.urlopen(  # noqa: S310 - pinned HTTPS asset
                    manifest["license_url"],
                    timeout=60,
                ) as response:
                    target.write_bytes(response.read())
            else:
                from huggingface_hub import hf_hub_download  # noqa: PLC0415

                cached = hf_hub_download(
                    manifest["repo_id"],
                    filename,
                    revision=manifest["revision"],
                    token=False,
                )
                shutil.copyfile(cached, target)
        validate_bundle(staged, manifest["files"])
        # Only publish files after the entire pinned snapshot is validated.
        shutil.copytree(staged, destination, dirs_exist_ok=True)
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=pathlib.Path)
    args = parser.parse_args()
    print(prepare(args.source))  # noqa: T201 - build CLI output
