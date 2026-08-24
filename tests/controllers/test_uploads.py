from __future__ import annotations

import asyncio

import pytest

from ntk.controllers.uploads import (
    UploadRequirements,
    UploadValidationError,
    materialize_uploads,
)


class Upload:
    def __init__(self, filename: str | None, content: bytes = b"content") -> None:
        self.filename = filename
        self.content = content

    async def read(self) -> bytes:
        return self.content


def test_materialize_uploads_writes_valid_files() -> None:
    async def materialize() -> None:
        async with materialize_uploads(
            [Upload("manual.pdf", b"pdf")],
            UploadRequirements(
                allowed_suffixes=frozenset({".pdf"}),
                file_description="PDF file",
                directory_prefix="ntk-test-",
                default_filename=lambda index: f"upload-{index}.pdf",
                reject_empty=True,
            ),
        ) as uploads:
            assert uploads.directory.is_dir()
            assert uploads.paths[0].name == "manual.pdf"
            assert uploads.paths[0].read_bytes() == b"pdf"

    asyncio.run(materialize())


@pytest.mark.parametrize(
    ("files", "message"),
    [
        ([], "At least one PDF file"),
        ([Upload("manual.csv")], "not a PDF file"),
        ([Upload("manual.pdf", b"")], "is empty"),
    ],
)
def test_materialize_uploads_rejects_invalid_files(
    files: list[Upload],
    message: str,
) -> None:
    async def materialize() -> None:
        async with materialize_uploads(
            files,
            UploadRequirements(
                allowed_suffixes=frozenset({".pdf"}),
                file_description="PDF file",
                directory_prefix="ntk-test-",
                default_filename=lambda index: f"upload-{index}.pdf",
                reject_empty=True,
            ),
        ):
            pytest.fail("Invalid uploads should not be materialized")

    with pytest.raises(UploadValidationError, match=message):
        asyncio.run(materialize())
