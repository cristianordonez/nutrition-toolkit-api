from __future__ import annotations


def require_id(value: int | None) -> int:
    """Return a persisted integer ID or fail for an unflushed model."""
    if value is None:
        msg = "Database ID is unavailable before the model is persisted"
        raise RuntimeError(msg)
    return value
