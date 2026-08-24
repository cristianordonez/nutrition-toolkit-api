from __future__ import annotations

import typing

if typing.TYPE_CHECKING:
    import pathlib


class CsvReader:
    def __init__(self, path: pathlib.Path) -> None:
        """Initialize the reader.

        :param path: Full path to file.
        :raises ValueError: file does not exist
        :raises ValueError: file does not have .pdf extension
        """
        if not path.is_file():
            msg = f"CSV file does not exist: {path}"
            raise ValueError(msg)
        if path.suffix.lower() != ".csv":
            msg = f"Path is not a csv file: {path}"
            raise ValueError(msg)
