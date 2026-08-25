from __future__ import annotations

import pytest

from ntk import controllers
from ntk.controllers import registry
from ntk.controllers.base import BaseController, BaseControllerGroup


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


def test_register_command_rejects_duplicate_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(registry, "COMMAND_REGISTRY", {})

    class CommandGroup(BaseControllerGroup):
        name = "duplicate"
        help = "Duplicate command group"

        @property
        def subcommands(self) -> list[BaseController]:
            return []

    registry.register_command_group(CommandGroup)
    with pytest.raises(ValueError, match="already registered"):
        registry.register_command_group(CommandGroup)


def test_register_command_rejects_non_group() -> None:
    class Command:
        name = "not-a-group"

    with pytest.raises(TypeError, match="must inherit from BaseControllerGroup"):
        registry.register_command_group(Command)  # ty: ignore[invalid-argument-type]
