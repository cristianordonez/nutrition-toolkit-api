"""Guard the universal Person terminology while allowing source vocabulary."""

from __future__ import annotations

import re
from pathlib import Path

_SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"
_LEGACY_PATTERN = re.compile(
    r"\bResident\b|\bresident_id\b|resident_identifier|resident_",
)


def test_internal_source_uses_person_terminology() -> None:
    unexpected: list[str] = []
    for path in _SOURCE_ROOT.rglob("*.py"):
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(),
            start=1,
        ):
            if not _LEGACY_PATTERN.search(line):
                continue
            relative = path.relative_to(_SOURCE_ROOT)
            source_specific = str(relative).startswith(
                "ntk/pipelines/person/ingestion/extract/",
            )
            explicitly_external = (
                "facility_resident_identifier" in line
                or '"Resident' in line
                or 'r"Resident' in line
                or 'r"\\bResident' in line
                or 'r"^\\s*Resident' in line
            )
            if not (source_specific and explicitly_external):
                unexpected.append(f"{relative}:{line_number}: {line.strip()}")

    assert unexpected == []


def test_internal_python_paths_do_not_use_resident_names() -> None:
    paths = [
        str(path.relative_to(_SOURCE_ROOT))
        for path in _SOURCE_ROOT.rglob("*.py")
        if "resident" in str(path.relative_to(_SOURCE_ROOT)).casefold()
    ]

    assert paths == []
