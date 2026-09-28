"""Refuse distributable engine artifacts that omit the offline model or data."""

# ruff: noqa: INP001 - Hatch loads this standalone build hook

from __future__ import annotations

import json
import pathlib
import runpy
import typing

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class BundledModelHook(BuildHookInterface):
    """Validate model and reference-database files and include them.

    Both are git-ignored build inputs, so they are force-included here.
    """

    def initialize(self, version: str, build_data: dict[str, typing.Any]) -> None:
        if self.target_name == "wheel" and version == "editable":
            # Allow uv sync before the developer prepares the model assets.
            return
        root = pathlib.Path(self.root)
        assets = root / "src/engine/assets/models"
        manifest = json.loads((assets / "minilm.json").read_text(encoding="utf-8"))
        directory = assets / manifest["directory"]
        helpers = runpy.run_path(str(root / "scripts/prepare_embedding_model.py"))
        try:
            helpers["validate_bundle"](directory, manifest["files"])
        except RuntimeError as error:
            msg = (
                f"{error}. Run apps/desktop/engine/scripts/prepare_embedding_model.py "
                "before building the engine. Builds never download model assets."
            )
            raise RuntimeError(msg) from error
        prefix = "engine" if self.target_name == "wheel" else "src/engine"
        for filename in manifest["files"]:
            build_data["force_include"][str(directory / filename)] = (
                f"{prefix}/assets/models/{manifest['directory']}/{filename}"
            )
        reference = root / "src/engine/assets/reference/facts.db"
        if not reference.is_file():
            msg = (
                f"Bundled reference database is missing: {reference}. Run "
                "apps/desktop/engine/scripts/build_reference_database.py "
                "before building the engine."
            )
            raise RuntimeError(msg)
        build_data["force_include"][str(reference)] = (
            f"{prefix}/assets/reference/facts.db"
        )
