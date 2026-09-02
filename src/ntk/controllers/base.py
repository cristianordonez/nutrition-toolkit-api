"""Base class for all controllers."""

from __future__ import annotations

import argparse
import types
import typing
from abc import ABC, abstractmethod
from types import GenericAlias

from pydantic_core import PydanticUndefined

if typing.TYPE_CHECKING:
    from ntk.models.base import CustomBaseSettings
    from ntk.models.output import Output

T = typing.TypeVar("T", bound="CustomBaseSettings")


class BaseController(ABC, typing.Generic[T]):
    """Base Controller class. Each represents a CLI command."""

    name: typing.ClassVar[str]
    help: typing.ClassVar[str]
    options_model: type[CustomBaseSettings] | None = None

    def register(self, subparser: argparse._SubParsersAction) -> None:
        """Register command as CLI command.

        :param subparser: ArgumentParser.add_subparser()
        """
        parser = subparser.add_parser(
            self.name,
            help=self.help,
            formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        )
        self.add_arguments(parser)
        parser.set_defaults(func=self.run, options_model=self.options_model)
        return parser

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        """Configure command arguments.

        :param parser: ArgumentParser instance
        """
        if self.options_model is not None:
            for name, field in self.options_model.model_fields.items():
                annotation = field.annotation
                origin = typing.get_origin(annotation)
                required = field.default is PydanticUndefined
                kwargs = {"help": field.description, "required": required}
                kwargs["default"] = field.default
                default_args = typing.get_args(annotation)
                if annotation is bool:
                    kwargs["action"] = "store_true"
                elif origin is typing.Literal:
                    kwargs["choices"] = typing.get_args(annotation)
                elif origin is list:
                    kwargs["nargs"] = "+"
                    kwargs["type"] = default_args[0]
                elif origin is tuple:
                    kwargs["nargs"] = len(default_args)
                    kwargs["type"] = default_args[0]
                elif (
                    origin is typing.Union or origin is types.UnionType
                ):  # account for None type
                    if isinstance(
                        default_args[0],
                        GenericAlias,
                    ):  # when type is tuple | None
                        arg_type = typing.get_args(default_args[0])  # inner tuple type
                        kwargs["nargs"] = "+"
                        kwargs["type"] = arg_type[0]
                    else:
                        kwargs["type"] = default_args[0]
                else:
                    kwargs["type"] = annotation
                parser.add_argument(
                    f"--{name.replace('_', '-')}",
                    **kwargs,  # ty: ignore[invalid-argument-type]
                )

    @abstractmethod
    def run(self, options: T) -> Output | typing.Awaitable[Output]:
        """Run the command."""


class BaseControllerGroup(BaseController):
    """CLI command."""

    @property
    @abstractmethod
    def subcommands(self) -> list[BaseController]:
        """Child commands under group.

        :return: list of BaseController instances
        """
        return self.subcommands

    def register(self, subparser: argparse._SubParsersAction) -> None:
        """Register subcommands.

        :param subparsers: Add subcommands to current command
        """
        parser = subparser.add_parser(self.name, help=self.help)
        self.add_arguments(parser)
        child_subparser = parser.add_subparsers(
            dest=f"{self.name}_command",
            required=True,
        )
        for command in self.subcommands:
            command.register(child_subparser)

    def run(self, options: T) -> Output:
        """Run the command."""
        raise NotImplementedError("Command Group not called")
