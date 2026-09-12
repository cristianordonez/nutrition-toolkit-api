"""Contains all CLI command and command groups."""

from __future__ import annotations

import importlib

_COMMAND_GROUP_MODULES = (
    "ntk.controllers.assessment.app",
    "ntk.controllers.calculate.app",
    "ntk.controllers.documents.app",
    "ntk.controllers.key.app",
    "ntk.controllers.knowledge.app",
    "ntk.controllers.persons.app",
    "ntk.controllers.tubefeed.app",
)


def load_command_groups() -> None:
    """Autoimport all commands so that they appear in registry.

    :param package_name: name of package to import all classes from
    """
    for module_name in _COMMAND_GROUP_MODULES:
        importlib.import_module(module_name)
