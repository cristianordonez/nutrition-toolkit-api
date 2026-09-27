"""Contains all CLI command and command groups."""

from __future__ import annotations

import importlib

_COMMAND_GROUP_MODULES = (
    "server.controllers.ncp.app",
    "server.controllers.calculate.app",
    "server.controllers.key.app",
    "server.controllers.knowledge.app",
)


def load_command_groups() -> None:
    """Autoimport all commands so that they appear in registry.

    :param package_name: name of package to import all classes from
    """
    for module_name in _COMMAND_GROUP_MODULES:
        importlib.import_module(module_name)
