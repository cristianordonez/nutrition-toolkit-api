"""Guard the universal Person terminology while allowing source vocabulary."""

from __future__ import annotations

import re
from pathlib import Path

_SOURCE_ROOTS = [
    Path(__file__).resolve().parents[4] / "packages/ntk-core/src",
    Path(__file__).resolve().parents[4] / "apps/cloud-api/src",
    Path(__file__).resolve().parents[2] / "src",
]
_LEGACY_PATTERN = re.compile(
    r"\bResident\b|\bresident_id\b|resident_identifier|resident_",
)
_PROGRESS_NOTE_PATTERN = re.compile(
    r"progress[ _-]?notes?|ProgressNotes?|ProgressNote",
    re.IGNORECASE,
)


def test_internal_source_uses_person_terminology() -> None:
    unexpected: list[str] = []
    for source_root in _SOURCE_ROOTS:
        for path in source_root.rglob("*.py"):
            for line_number, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(),
                start=1,
            ):
                if not _LEGACY_PATTERN.search(line):
                    continue
                relative = path.relative_to(source_root)
                source_specific = str(relative).startswith(
                    "engine/pipelines/person/ingestion/extract/",
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
        str(path.relative_to(source_root))
        for source_root in _SOURCE_ROOTS
        for path in source_root.rglob("*.py")
        if "resident" in str(path.relative_to(source_root)).casefold()
    ]

    assert paths == []


def test_progress_note_terminology_is_limited_to_the_pcc_extractor() -> None:
    unexpected: list[str] = []
    for source_root in _SOURCE_ROOTS:
        paths = [*source_root.rglob("*.py"), *source_root.rglob("*.md")]
        for path in paths:
            relative = path.relative_to(source_root)
            for line_number, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(),
                start=1,
            ):
                if not _PROGRESS_NOTE_PATTERN.search(line):
                    continue
                extractor_implementation = str(relative).endswith(
                    "pipelines/person/ingestion/extract/pcc_progress_notes.py",
                )
                extractor_reference = any(
                    name in line
                    for name in (
                        "pcc_progress_notes",
                        "PccProgressNotesExtractor",
                        "ParsedProgressNote",
                        "PreparedProgressNoteExtraction",
                    )
                )
                if not (extractor_implementation or extractor_reference):
                    unexpected.append(f"{relative}:{line_number}: {line.strip()}")

    assert unexpected == []
