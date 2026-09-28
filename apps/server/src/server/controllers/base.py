"""Base class for all controllers."""

from __future__ import annotations

import argparse
import types
import typing
from abc import ABC, abstractmethod
from types import GenericAlias

from pydantic_core import PydanticUndefined

if typing.TYPE_CHECKING:
    from server.models.base import CustomBaseSettings
    from server.models.output import Output

T = typing.TypeVar("T", bound="CustomBaseSettings")


def _annotation_kwargs(annotation: object) -> dict[str, typing.Any]:
    """Translate one field's type annotation into argparse keywords.

    Split out from ``add_arguments`` so each supported shape reads on its own
    and the caller stays a plain loop over the model's fields.
    """
    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)

    if annotation is bool:
        # A flag, so it can only ever be turned on. A setting that must also
        # be turned off needs an explicit Literal of its states instead.
        return {"action": "store_true"}
    if origin is typing.Literal:
        return {"choices": args}
    if origin is list:
        # argparse calls `type` as a converter, and `typing.Any` is not
        # callable. A list[Any] field takes whatever the shell gives us, so
        # leave the values as strings.
        variadic: dict[str, typing.Any] = {"nargs": "+"}
        if args[0] is not typing.Any:
            variadic["type"] = args[0]
        return variadic
    if origin is tuple:
        return {"nargs": len(args), "type": args[0]}
    if origin is typing.Union or origin is types.UnionType:
        return _optional_kwargs(args[0])
    return {"type": annotation}


def _optional_kwargs(inner: object) -> dict[str, typing.Any]:
    """Translate the value type of an optional field, e.g. ``X | None``."""
    if isinstance(inner, GenericAlias):  # when type is tuple | None
        return {"nargs": "+", "type": typing.get_args(inner)[0]}
    if typing.get_origin(inner) is typing.Literal:
        # An optional Literal, e.g. `Literal["on", "off"] | None` for a flag
        # that may be left unset. argparse calls `type` as a converter and a
        # Literal is not callable, so this is a choices constraint just as a
        # bare Literal is.
        return {"choices": typing.get_args(inner)}
    return {"type": inner}


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
        if self.options_model is None:
            return
        for name, field in self.options_model.model_fields.items():
            kwargs: dict[str, typing.Any] = {
                "help": field.description,
                "required": field.default is PydanticUndefined,
                "default": field.default,
            }
            kwargs.update(_annotation_kwargs(field.annotation))
            parser.add_argument(
                f"--{name.replace('_', '-')}",
                **kwargs,
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
