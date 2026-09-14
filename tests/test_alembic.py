from __future__ import annotations

import os
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlmodel import SQLModel

# Register every table before comparing a migrated database with model metadata.
import ntk.models.sql  # noqa: F401
from alembic import command

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_REVISIONS = [
    "20260912_0000",
    "20260912_0001",
    "20260912_0002",
    "20260913_0003",
]


def _config(database_url: str | None = None) -> Config:
    config = Config(PROJECT_ROOT / "alembic.ini")
    if database_url is not None:
        config.attributes["connection_url"] = database_url
    return config


def test_revision_history_is_linear_and_has_one_head() -> None:
    scripts = ScriptDirectory.from_config(_config())

    assert scripts.get_heads() == [EXPECTED_REVISIONS[-1]]
    assert [revision.revision for revision in scripts.walk_revisions()][::-1] == (
        EXPECTED_REVISIONS
    )
    assert [
        revision.revision
        for revision in scripts.iterate_revisions("head", "20260912_0001")
    ] == ["20260913_0003", "20260912_0002"]


def test_offline_upgrade_renders_singleton_diet_constraint(
    capsys: pytest.CaptureFixture[str],
) -> None:
    command.upgrade(_config(), "head", sql=True)

    sql = capsys.readouterr().out
    assert sql.index("CREATE EXTENSION IF NOT EXISTS vector") < sql.index(
        "CREATE TABLE knowledge_chunks_embeddings",
    )
    assert "CREATE TABLE person (" in sql
    assert "CREATE TABLE extracted_fact (" in sql
    assert "DROP CONSTRAINT person_diet_person_id_state_key_key" in sql
    assert "ADD CONSTRAINT person_diet_person_id_key UNIQUE (person_id)" in sql
    assert (
        "ALTER TABLE person_assessment RENAME TO person_nutrition_care_process" in sql
    )
    assert "assessment_source TO ncp_source" in sql
    assert "person_assessment_id TO person_nutrition_care_process_id" in sql
    assert "person_progress_note RENAME TO person_clinical_note" in sql
    assert "progress_note_id TO clinical_note_id" in sql
    assert "person_nutrition_clinical_note_embeddings" in sql
    assert "DROP TABLE person_nutrition_care_process" in sql


@pytest.mark.skipif(
    "NTK_ALEMBIC_TEST_DATABASE_URL" not in os.environ,
    reason="set NTK_ALEMBIC_TEST_DATABASE_URL to an empty disposable PostgreSQL DB",
)
def test_postgresql_fresh_upgrade_matches_metadata_and_preserves_legacy_data() -> None:
    """Exercise fresh creation and the legacy adoption path on PostgreSQL."""
    database_url = os.environ["NTK_ALEMBIC_TEST_DATABASE_URL"]
    engine = sa.create_engine(database_url)
    inspector = sa.inspect(engine)
    existing_tables = set(inspector.get_table_names())
    assert not existing_tables, (
        "NTK_ALEMBIC_TEST_DATABASE_URL must reference an empty disposable database; "
        f"found {sorted(existing_tables)}"
    )

    config = _config(database_url)
    command.upgrade(config, "head")
    command.upgrade(config, "head")

    with engine.connect() as connection:
        inspector = sa.inspect(connection)
        assert set(inspector.get_table_names()) == {
            *SQLModel.metadata.tables,
            "alembic_version",
        }
        assert connection.scalar(
            sa.text(
                "SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')",
            ),
        )
        migration_context = MigrationContext.configure(
            connection,
            opts={
                "compare_type": True,
                "include_name": lambda name, type_, _parents: (
                    not (type_ == "table" and name in {"alembic_version", "session"})
                ),
            },
        )
        assert compare_metadata(migration_context, SQLModel.metadata) == []

    # Prove the complete downgrade path, then exercise consolidation of both
    # imported and generated NCP rows from the preceding revision.
    command.downgrade(config, "base")
    command.upgrade(config, "20260912_0002")
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                """
                INSERT INTO person (
                    id, name, first_name, last_name, normalized_first_name,
                    normalized_last_name, created_at
                ) VALUES (
                    1, 'Test Person', 'Test', 'Person', 'test', 'person', NOW()
                );
                INSERT INTO person_progress_note (
                    id, person_id, note_date, note_type, author, note_text,
                    raw_text, note_key, extraction_status
                ) VALUES (
                    10, 1, NOW(), 'Dietitian Progress Note', 'RD',
                    'Imported nutrition note', 'Imported nutrition note',
                    'legacy-note', 'extracted'
                );
                INSERT INTO person_nutrition_care_process (
                    id, person_id, source_progress_note_id, content, ncp_source,
                    content_hash, ncp_index, ncp_date, created_by, status,
                    created_at
                ) VALUES
                    (20, 1, 10, 'Imported nutrition note', 'imported',
                     'imported-hash', 0, DATE '2026-09-12', 'RD', 'finalized',
                     NOW()),
                    (21, 1, NULL, 'Generated nutrition note', 'generated',
                     'generated-hash', 0, DATE '2026-09-13', 'model', 'finalized',
                     NOW());
                INSERT INTO person_nutrition_care_process_embeddings (
                    person_nutrition_care_process_id, embedding_vector,
                    model_name, created_at
                ) VALUES
                    (20, array_fill(0::real, ARRAY[384])::vector, 'model', NOW()),
                    (21, array_fill(0::real, ARRAY[384])::vector, 'model', NOW())
                """,
            ),
        )
    command.upgrade(config, "head")
    command.upgrade(config, "head")

    with engine.connect() as connection:
        inspector = sa.inspect(connection)
        assert "person_assessment" not in inspector.get_table_names()
        assert "person_nutrition_care_process" not in inspector.get_table_names()
        assert "person_clinical_note" in inspector.get_table_names()
        notes = connection.execute(
            sa.text(
                "SELECT note_text, ncp_source FROM person_clinical_note "
                "ORDER BY note_text",
            ),
        ).all()
        assert notes == [
            ("Generated nutrition note", "generated"),
            ("Imported nutrition note", "imported"),
        ]
        embeddings = connection.execute(
            sa.text(
                "SELECT type FROM person_nutrition_clinical_note_embeddings "
                "ORDER BY type",
            ),
        ).scalars()
        assert list(embeddings) == ["Dietician", "Nutrition/Dietary"]
