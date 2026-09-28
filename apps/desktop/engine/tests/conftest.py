from __future__ import annotations

import os

_TEST_SETTINGS: dict[str, str] = {}


def pytest_configure() -> None:
    """Provide safe defaults before pytest imports application test modules."""
    for key, value in _TEST_SETTINGS.items():
        os.environ.setdefault(key, value)
