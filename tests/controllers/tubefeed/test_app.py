from __future__ import annotations

import argparse

from ntk.controllers.registry import COMMAND_REGISTRY
from ntk.controllers.tubefeed.app import TubefeedControllerGroup
from ntk.controllers.tubefeed.calculate import CalculateTubefeedController


def test_tubefeed_controller_group_is_registered() -> None:
    assert "tubefeed" in COMMAND_REGISTRY
    assert COMMAND_REGISTRY["tubefeed"] is TubefeedControllerGroup


def test_tubefeed_controller_group_subcommands() -> None:
    group = TubefeedControllerGroup()

    assert [type(command) for command in group.subcommands] == [
        CalculateTubefeedController,
    ]
    assert [command.name for command in group.subcommands] == ["calculate"]


def test_tubefeed_controller_group_registers_subparsers() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")
    group = TubefeedControllerGroup()
    group.register(subparsers)

    parsed = parser.parse_args(
        [
            "tubefeed",
            "calculate",
            "--formula",
            "jevity",
        ],
    )

    assert parsed.command == "tubefeed"
    assert parsed.tubefeed_command == "calculate"
    assert parsed.formula == "jevity"
