"""Create new alembic migration with the tox 'migration' environment name.

tox -e migration -- "add person tables"
"""

from __future__ import annotations

import pathlib
import re
import shutil
import subprocess
import sys
from datetime import UTC, datetime

VERSIONS_DIR = pathlib.Path("alembic/versions")


def next_revision_id() -> str:
    today = datetime.now(tz=UTC).strftime("%Y%m%d")
    pattern = re.compile(rf"^{today}_(\d{{4}})_")

    numbers: list[int] = []

    if VERSIONS_DIR.exists():
        for path in VERSIONS_DIR.glob("*.py"):
            match = pattern.match(path.name)
            if match:
                numbers.append(int(match.group(1)))

    next_number = max(numbers, default=0) + 1
    return f"{today}_{next_number:04d}"


def main() -> None:
    args_len = 2
    if len(sys.argv) < args_len:
        msg = ('Usage: tox -e migration -- "migration description"',)
        raise SystemExit(msg)
    executable_path = shutil.which("uv")
    message = " ".join(sys.argv[1:])
    revision_id = next_revision_id()
    subprocess.run(  # noqa: S603
        [
            executable_path,
            "run",
            "alembic",
            "revision",
            "--autogenerate",
            "--rev-id",
            revision_id,
            "-m",
            message,
        ],
        check=True,
    )


if __name__ == "__main__":
    main()
