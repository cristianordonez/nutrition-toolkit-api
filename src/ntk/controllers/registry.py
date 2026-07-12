from __future__ import annotations

import typing

if typing.TYPE_CHECKING:
    from collections.abc import Callable

    from .base import BaseController

T = typing.TypeVar("T", bound="BaseController")

COMMAND_REGISTRY: dict[str, type[BaseController]] = {}


def register_command() -> Callable[[type[T]], type[T]]:
    """Class decorator to register command.

    :param name: name of command
    :return: class instance
    """

    def decorator(cls: type[T]) -> type[T]:
        if cls.name in COMMAND_REGISTRY:
            msg = f"Command {cls.name} already registered"
            raise ValueError(msg)
        COMMAND_REGISTRY[cls.name] = cls
        return cls

    return decorator
