"""Controller-layer support for materializing uploaded documents."""

from __future__ import annotations

import contextlib
import pathlib
import typing
from dataclasses import dataclass
from tempfile import TemporaryDirectory


class ReadableUpload(typing.Protocol):
    """Minimal upload interface required by document controllers."""

    filename: str | None

    async def read(self) -> bytes:
        """Return the uploaded file contents."""
        ...


class UploadValidationError(ValueError):
    """Raised when uploaded documents do not match controller requirements."""


@dataclass(frozen=True)
class MaterializedUploads:
    """Temporary folder and paths created from uploaded documents."""

    directory: pathlib.Path
    paths: list[pathlib.Path]


@dataclass(frozen=True)
class UploadRequirements:
    """Validation and naming requirements for one upload workflow."""

    allowed_suffixes: frozenset[str]
    file_description: str
    directory_prefix: str
    default_filename: typing.Callable[[int], str]
    reject_empty: bool = False


@contextlib.asynccontextmanager
async def materialize_uploads(
    files: typing.Sequence[ReadableUpload],
    requirements: UploadRequirements,
) -> typing.AsyncIterator[MaterializedUploads]:
    """Validate uploads and write them to a temporary controller workspace."""
    if not files:
        msg = f"At least one {requirements.file_description} is required"
        raise UploadValidationError(msg)

    with TemporaryDirectory(prefix=requirements.directory_prefix) as directory:
        folder = pathlib.Path(directory)
        paths: list[pathlib.Path] = []
        used_filenames: set[str] = set()
        for index, upload in enumerate(files):
            filename = pathlib.Path(
                upload.filename or requirements.default_filename(index),
            ).name
            if (
                pathlib.Path(filename).suffix.lower()
                not in requirements.allowed_suffixes
            ):
                msg = f"'{filename}' is not a {requirements.file_description}"
                raise UploadValidationError(msg)
            content = await upload.read()
            if requirements.reject_empty and not content:
                msg = f"'{filename}' is empty"
                raise UploadValidationError(msg)
            path = _unique_upload_path(folder, filename, used_filenames)
            path.write_bytes(content)
            paths.append(path)
        yield MaterializedUploads(directory=folder, paths=paths)


def _unique_upload_path(
    folder: pathlib.Path,
    filename: str,
    used_filenames: set[str],
) -> pathlib.Path:
    """Return a collision-safe path for one upload in a shared directory."""
    source = pathlib.Path(filename)
    candidate = source.name
    sequence = 2
    while candidate.casefold() in used_filenames:
        candidate = f"{source.stem}-{sequence}{source.suffix}"
        sequence += 1
    used_filenames.add(candidate.casefold())
    return folder / candidate
