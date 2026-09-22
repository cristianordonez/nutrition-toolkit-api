"""The CLI's stdout is a machine-readable contract, so nothing else may use it.

The desktop shell parses stdout as JSON. Anything else that writes there --
Logfire's console exporter is the one that has actually bitten us -- corrupts
that contract, and only for the commands that trigger it, so it surfaces as a
puzzling parse error rather than an obvious failure.
"""

from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
import typing

import logfire

import engine.presentation.cli.app as cli_app

if typing.TYPE_CHECKING:
    import pathlib

    import pytest


def test_logfire_console_output_is_not_stdout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Logfire's console exporter defaults to stdout; it must be moved off it."""
    captured: dict[str, typing.Any] = {}
    monkeypatch.setattr(logfire, "configure", lambda **kwargs: captured.update(kwargs))

    importlib.reload(cli_app)

    console = captured.get("console")
    assert console is not None, "logfire.configure() was called without console options"
    assert console.output is sys.stderr


def test_a_command_prints_only_its_json_result(tmp_path: pathlib.Path) -> None:
    """End-to-end: a real CLI run leaves stdout parseable on its own."""
    completed = subprocess.run(
        [sys.executable, "-m", "engine.presentation.cli.app", "tubefeed", "formulas"],
        capture_output=True,
        text=True,
        check=False,
        env={
            **os.environ,
            # Seed and read a throwaway catalog rather than the developer's own.
            "NTK_FACTS_DATABASE_PATH": str(tmp_path / "facts.db"),
            "NTK_SETTINGS_DATABASE_PATH": str(tmp_path / "settings.db"),
        },
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["formulas"], "expected the seeded catalog"
