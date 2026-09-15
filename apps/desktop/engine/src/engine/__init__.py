from __future__ import annotations

from importlib.metadata import version

__version__ = version("engine")

__all__: list[str] = ["__version__"]
