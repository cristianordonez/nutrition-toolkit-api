"""Contains all CLI command and command groups."""

from __future__ import annotations

import importlib

_COMMAND_GROUP_MODULES = (
    "engine.controllers.demo.app",
    "engine.controllers.documents.app",
    "engine.controllers.ncp.app",
    "engine.controllers.persons.app",
    "engine.controllers.tubefeed.app",
)


def load_command_groups() -> None:
    """Autoimport all commands so that they appear in registry.

    :param package_name: name of package to import all classes from
    """
    for module_name in _COMMAND_GROUP_MODULES:
        importlib.import_module(module_name)
