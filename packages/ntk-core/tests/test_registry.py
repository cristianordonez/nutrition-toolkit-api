from __future__ import annotations

import pytest

from ntk.controllers import registry
from ntk.controllers.base import BaseController, BaseControllerGroup


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
