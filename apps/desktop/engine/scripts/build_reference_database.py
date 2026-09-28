"""Build-time only: stage the starter database shipped with the engine.

Copies a curated ``facts.db`` -- by default the configured one -- to
``src/engine/assets/reference/facts.db``, where a fresh install starts from it.
It must hold reference data only: the knowledge base, NCP style examples and
their vectors, and the enteral formula catalog. The build refuses, rather than
scrubs, a database with anything else in it, so a resident's record can never
be shipped by running this against the wrong file.

The user's own settings row is dropped; startup seeds the defaults.
"""

# ruff: noqa: INP001, T201 - standalone build script

from __future__ import annotations

import argparse
import pathlib
import sqlite3
import tempfile

import sqlite_vec

_DESTINATION = (
    pathlib.Path(__file__).resolve().parents[1] / "src/engine/assets/reference/facts.db"
)

#: Tables allowed to hold rows in the shipped database. Everything else --
#: people, facilities, documents, clinical sources and facts -- must be empty.
_REFERENCE_TABLES = frozenset(
    {
        "alembic_version",
        "enteral_formula",
        "enteral_formula_nutrient",
        "knowledge",
        "knowledge_chunk",
        "ncp_note",
        "settings",
    },
)
#: vec0 indexes and their shadow tables, named after the index.
_VECTOR_PREFIXES = ("knowledge_chunk_vector", "ncp_note_vector")


def _connect(path: pathlib.Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.enable_load_extension(True)  # noqa: FBT003
    try:
        sqlite_vec.load(connection)
    finally:
        connection.enable_load_extension(False)  # noqa: FBT003
    return connection


def validate_reference(connection: sqlite3.Connection) -> dict[str, int]:
    """Return row counts, refusing any data that is not reference data."""
    tables = [
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name",
        )
    ]
    counts = {
        table: connection.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]  # noqa: S608
        for table in tables
    }
    problems = [
        f"{table} has {count} row(s)"
        for table, count in counts.items()
        if count
        and table not in _REFERENCE_TABLES
        and not table.startswith(_VECTOR_PREFIXES)
    ]
    attached = connection.execute(
        "SELECT count(*) FROM ncp_note WHERE status != 'example' "
        "OR person_id IS NOT NULL OR facility_id IS NOT NULL",
    ).fetchone()[0]
    if attached:
        problems.append(f"ncp_note has {attached} note(s) that are not examples")
    for source, index, key in (
        ("knowledge_chunk", "knowledge_chunk_vector", "knowledge_chunk_id"),
        ("ncp_note", "ncp_note_vector", "ncp_note_id"),
    ):
        missing = connection.execute(
            f"SELECT count(*) FROM {source} WHERE id NOT IN "  # noqa: S608
            f"(SELECT {key} FROM {index})",
        ).fetchone()[0]
        if missing:
            problems.append(f"{missing} {source} row(s) have no vector")
    if problems:
        msg = "Not a reference-only database: " + "; ".join(problems)
        raise RuntimeError(msg)
    return counts


def build(source: pathlib.Path, destination: pathlib.Path = _DESTINATION) -> None:
    """Copy, check and compact ``source`` into the shipped reference database."""
    if not source.is_file():
        msg = f"Source database does not exist: {source}"
        raise FileNotFoundError(msg)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as temporary:
        staged = pathlib.Path(temporary) / destination.name
        # VACUUM INTO takes a consistent snapshot, WAL contents included,
        # without writing to the source.
        source_connection = _connect(source)
        try:
            source_connection.execute("VACUUM INTO ?", (str(staged),))
        finally:
            source_connection.close()

        connection = _connect(staged)
        try:
            counts = validate_reference(connection)
            connection.execute("DELETE FROM settings")
            connection.commit()
            # A single self-contained file: no -wal beside it to ship.
            connection.execute("PRAGMA journal_mode = DELETE")
            connection.execute("VACUUM")
            (check,) = connection.execute("PRAGMA integrity_check").fetchone()
            if check != "ok":
                msg = f"Reference database failed its integrity check: {check}"
                raise RuntimeError(msg)
        finally:
            connection.close()
        staged.replace(destination)

    print(f"Wrote {destination} ({destination.stat().st_size / 1e6:.1f} MB)")
    for table in ("knowledge", "knowledge_chunk", "ncp_note", "enteral_formula"):
        print(f"  {table}: {counts.get(table, 0)}")


def main() -> None:
    """Build from ``--source``, defaulting to the configured database."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=pathlib.Path)
    args = parser.parse_args()
    source = args.source
    if source is None:
        from engine.models.settings import SETTINGS  # noqa: PLC0415

        source = SETTINGS.database_path.expanduser()
    build(source)


if __name__ == "__main__":
    main()
