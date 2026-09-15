from __future__ import annotations

import os

_TEST_SETTINGS = {
    "NTK_OPEN_AI_API_KEY": "test-openai-key",
}


def pytest_configure() -> None:
    """Provide safe defaults before pytest imports application test modules."""
    for key, value in _TEST_SETTINGS.items():
        os.environ.setdefault(key, value)
