from __future__ import annotations

import typing

from .base import BaseControllerGroup

ControllerGroupT = typing.TypeVar("ControllerGroupT", bound=BaseControllerGroup)

COMMAND_REGISTRY: dict[str, type[BaseControllerGroup]] = {}


def register_command_group(
    cls: type[ControllerGroupT],
) -> type[ControllerGroupT]:
    """Register a top-level CLI controller group and return its class."""
    if not issubclass(cls, BaseControllerGroup):
        msg = f"{cls.__name__} must inherit from BaseControllerGroup"
        raise TypeError(msg)
    if cls.name in COMMAND_REGISTRY:
        msg = f"Command group '{cls.name}' is already registered"
        raise ValueError(msg)
    COMMAND_REGISTRY[cls.name] = cls
    return cls
