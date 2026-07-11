from __future__ import annotations

# ruff: noqa: S101
import argparse

from ntk.controllers.calculate.app import CalculateControllerGroup
from ntk.controllers.registry import COMMAND_REGISTRY


def test_calculate_controller_group_is_registered() -> None:
    assert "calc" in COMMAND_REGISTRY
    assert COMMAND_REGISTRY["calc"] is CalculateControllerGroup


def test_calculate_controller_group_registers_subparsers() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")
    group = CalculateControllerGroup()
    group.register(subparsers)
    parsed = parser.parse_args(
        [
            "calc",
            "energy",
            "--weight",
            "150",
            "--height",
            "70",
            "--age",
            "30",
        ],
    )
    assert parsed.command == "calc"
    assert parsed.calc_command == "energy"
