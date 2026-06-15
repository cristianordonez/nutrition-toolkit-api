from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, TypeVar

from python_template.models.base import AppSettings

if TYPE_CHECKING:
    import argparse

T = TypeVar("T", bound="AppSettings")


class BaseCommand(ABC):
    name: str = ""
    help: str = ""
    options: type[AppSettings] | None = None

    def register(self, subparser: argparse._SubParsersAction) -> None:
        """Register command as CLI command

        :param subparser: ArgumentParser.add_subparser()
        """
        parser = subparser.add_parser(self.name, help=self.help)
        self.add_arguments(parser)
        parser.set_defaults(func=self.run)
        return parser

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        """Configure command arguments

        :param parser: ArgumentParser instance
        """
        if self.options is not None:
            for name, field in self.options.model_fields.items():
                annotation = field.annotation
                kwargs = {
                    "help": field.description,
                }
                if field.default is not None:
                    kwargs["default"] = field.default
                if annotation is bool:
                    kwargs["action"] = "store_true"
                else:
                    kwargs["type"] = annotation
                parser.add_argument(
                    f"--{name.replace('_', '-')}",
                    **kwargs,
                )

    @abstractmethod
    def run(self, args: argparse.Namespace) -> int:
        """Run the command"""


class BaseCommandGroup(BaseCommand):
    """CLI command."""

    subcommands: list[BaseCommand] = []

    def register(self, subparser: argparse._SubParsersAction) -> None:
        """Register subcommands

        :param subparsers: Add subcommands to current command
        """
        parser = subparser.add_parser(self.name, help=self.help)
        self.add_arguments(parser)
        child_subparser = parser.add_subparsers(
            dest=f"{self.name}_command", required=True
        )
        for command in self.subcommands:
            command.register(child_subparser)

    def run(self, args: argparse.Namespace) -> int:
        """Run the command"""
        raise NotImplementedError("Command Group not called")
