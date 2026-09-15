from __future__ import annotations

import pytest

from api import controllers


def test_load_command_groups_imports_configured_modules(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    imported: list[str] = []

    def import_module(name: str) -> object:
        imported.append(name)
        return object()

    monkeypatch.setattr(controllers.importlib, "import_module", import_module)

    controllers.load_command_groups()

    assert imported == list(controllers._COMMAND_GROUP_MODULES)  # noqa: SLF001
