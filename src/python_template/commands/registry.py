from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, TypeVar

if TYPE_CHECKING:
    from .base import BaseCommand

T = TypeVar("T", bound="BaseCommand")

COMMAND_REGISTRY: dict[str, type[BaseCommand]] = {}


def register_command() -> Callable[[type[T]], type[T]]:
    """Class decorator to register command

    :param name: name of command
    :return: class instance
    """

    def decorator(cls: type[T]) -> type[T]:
        if cls.name in COMMAND_REGISTRY:
            raise ValueError(f"Command {cls.name} already registered")
        COMMAND_REGISTRY[cls.name] = cls
        return cls

    return decorator
