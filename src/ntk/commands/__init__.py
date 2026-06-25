"""Contains all CLI command and command groups"""

from __future__ import annotations

import importlib
import pkgutil


def load_commands(package_name: str) -> None:
    """Autoimport all commands so that they appear in registry.

    :param package_name: name of package to import all classes from
    """
    package = importlib.import_module(package_name)
    for _, module_name, _ in pkgutil.walk_packages(
        package.__path__, package.__name__ + "."
    ):
        importlib.import_module(module_name)
