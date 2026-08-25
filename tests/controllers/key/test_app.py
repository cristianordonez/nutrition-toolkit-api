from __future__ import annotations

import argparse
import typing

from ntk.controllers.registry import COMMAND_REGISTRY

if typing.TYPE_CHECKING:
    from collections.abc import Callable


def test_key_controller_group_subcommands(
    load_controller_module: Callable[[str], typing.Any],
) -> None:
    COMMAND_REGISTRY.pop("key", None)
    app_module = load_controller_module("ntk.controllers.key.app")
    group = app_module.KeyControllerGroup()

    assert group.name == "key"
    assert group.help == "API Key controller group"
    assert [type(command) for command in group.subcommands] == [
        app_module.CreateController,
        app_module.ListController,
        app_module.RevokeController,
        app_module.GrantPermissionsController,
        app_module.RevokePermissionsController,
    ]
    assert [command.name for command in group.subcommands] == [
        "create",
        "list",
        "revoke",
        "grant-permissions",
        "revoke-permissions",
    ]
    assert COMMAND_REGISTRY["key"] is app_module.KeyControllerGroup


def test_key_controller_group_registers_subcommands(
    load_controller_module: Callable[[str], typing.Any],
) -> None:
    COMMAND_REGISTRY.pop("key", None)
    app_module = load_controller_module("ntk.controllers.key.app")
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")
    group = app_module.KeyControllerGroup()
    group.register(subparsers)
    args = parser.parse_args(
        ["key", "create", "--name", "demo", "--permissions", "read"],
    )
    assert args.key_command == "create"
    assert args.func is not None
    assert args.options_model is not None
