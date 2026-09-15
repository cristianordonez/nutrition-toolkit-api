from __future__ import annotations

import json
import pathlib
import typing

from pydantic import BaseModel


def require_id(value: int | None) -> int:
    """Return a persisted integer ID or fail for an unflushed model."""
    if value is None:
        msg = "Database ID is unavailable before the model is persisted"
        raise RuntimeError(msg)
    return value


def write_json(objects: list[typing.Any], file_path: str | pathlib.Path) -> None:
    """Write pydantic model to json file."""
    data = [
        obj.model_dump(mode="json") if isinstance(obj, BaseModel) else obj
        for obj in objects
    ]

    pathlib.Path(file_path).write_text(
        json.dumps(data, indent=2),
        encoding="utf-8",
    )
