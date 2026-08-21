from __future__ import annotations

from types import SimpleNamespace

import pytest

from ntk import controllers
from ntk.controllers import registry


def test_load_commands_imports_discovered_modules(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = SimpleNamespace(__path__=["commands"], __name__="example")
    imported: list[str] = []

    def import_module(name: str) -> object:
        imported.append(name)
        return package

    monkeypatch.setattr(controllers.importlib, "import_module", import_module)
    monkeypatch.setattr(
        controllers.pkgutil,
        "walk_packages",
        lambda *_: [(None, "example.first", False), (None, "example.second", False)],
    )

    controllers.load_commands("example")

    assert imported == ["example", "example.first", "example.second"]


def test_register_command_rejects_duplicate_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(registry, "COMMAND_REGISTRY", {})

    class Command:
        name = "duplicate"

    registry.register_command()(Command)  # ty: ignore[invalid-argument-type]
    with pytest.raises(ValueError, match="already registered"):
        registry.register_command()(Command)  # ty: ignore[invalid-argument-type]
