"""Merge Nutrition Care Processes into clinical-note storage.

Revision ID: 20260913_0003
Revises: 20260912_0002
Create Date: 2026-09-13
"""

from __future__ import annotations

import typing

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

if typing.TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "20260913_0003"
down_revision: str | Sequence[str] | None = "20260912_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _rename_index(old: str, new: str) -> None:
    op.execute(f'ALTER INDEX IF EXISTS "{old}" RENAME TO "{new}"')


def upgrade() -> None:
    """Consolidate notes and NCPs without retaining compatibility storage."""
    with op.get_context().autocommit_block():
        op.execute(
            "ALTER TYPE extraction_status ADD VALUE IF NOT EXISTS 'not_applicable'",
        )
    op.rename_table("person_progress_note", "person_clinical_note")
    op.execute(
        "ALTER SEQUENCE IF EXISTS person_progress_note_id_seq "
        "RENAME TO person_clinical_note_id_seq",
    )
    for suffix in (
        "extraction_status",
        "note_date",
        "note_key",
        "person_id",
        "source_id",
    ):
        _rename_index(
            f"ix_person_progress_note_{suffix}",
            f"ix_person_clinical_note_{suffix}",
        )

    op.alter_column(
        "extracted_fact",
        "progress_note_id",
        new_column_name="clinical_note_id",
    )
    _rename_index(
        "ix_extracted_fact_progress_note_id",
        "ix_extracted_fact_clinical_note_id",
    )

    op.add_column(
        "person_clinical_note",
        sa.Column(
            "ncp_source",
            sa.Enum(
                "generated",
                "imported",
                name="nutrition_care_process_source",
                native_enum=False,
                create_constraint=False,
            ),
            nullable=True,
        ),
    )
    op.add_column(
        "person_clinical_note",
        sa.Column("source_filename", sa.String(), nullable=True),
    )
    op.add_column(
        "person_clinical_note",
        sa.Column("content_hash", sa.String(), nullable=True),
    )
    op.add_column(
        "person_clinical_note",
        sa.Column("ncp_index", sa.Integer(), nullable=True),
    )
    op.add_column(
        "person_clinical_note",
        sa.Column("created_by", sa.String(), nullable=True),
    )
    op.add_column(
        "person_clinical_note",
        sa.Column(
            "status",
            postgresql.ENUM(
                "draft",
                "finalized",
                "discarded",
                name="nutrition_care_process_status",
                create_type=False,
            ),
            nullable=True,
        ),
    )
    op.add_column(
        "person_clinical_note",
        sa.Column("model_name", sa.String(), nullable=True),
    )
    op.add_column(
        "person_clinical_note",
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "person_clinical_note",
        sa.Column("finalized_at", sa.DateTime(), nullable=True),
    )

    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM person_nutrition_care_process n
                JOIN person_clinical_note c ON c.id = n.source_progress_note_id
                WHERE n.person_id <> c.person_id OR n.content <> c.note_text
            ) THEN
                RAISE EXCEPTION 'NCP and source clinical-note data conflict';
            END IF;
        END $$
        """,
    )
    op.execute(
        """
        CREATE TEMPORARY TABLE ncp_clinical_note_map (
            old_ncp_id INTEGER PRIMARY KEY,
            clinical_note_id INTEGER NOT NULL
        ) ON COMMIT DROP
        """,
    )
    op.execute(
        """
        INSERT INTO ncp_clinical_note_map (old_ncp_id, clinical_note_id)
        SELECT id, source_progress_note_id
        FROM person_nutrition_care_process
        WHERE source_progress_note_id IS NOT NULL
        """,
    )
    op.execute(
        """
        UPDATE person_clinical_note c
        SET ncp_source = n.ncp_source,
            source_filename = n.source_filename,
            content_hash = n.content_hash,
            ncp_index = n.ncp_index,
            created_by = n.created_by,
            status = n.status,
            model_name = n.model_name,
            created_at = n.created_at,
            finalized_at = n.finalized_at
        FROM person_nutrition_care_process n
        WHERE n.source_progress_note_id = c.id
        """,
    )
    op.execute(
        """
        DO $$
        DECLARE
            n RECORD;
            new_note_id INTEGER;
        BEGIN
            FOR n IN
                SELECT * FROM person_nutrition_care_process
                WHERE source_progress_note_id IS NULL
                ORDER BY id
            LOOP
                INSERT INTO person_clinical_note (
                    person_id, note_date, note_type, author, note_text, raw_text,
                    note_key, extraction_status, ncp_source, source_filename,
                    content_hash, ncp_index, created_by, status, model_name,
                    created_at, finalized_at
                ) VALUES (
                    n.person_id, n.ncp_date::timestamp, 'Nutrition/Dietary',
                    n.created_by, n.content, n.content,
                    'generated-ncp:migrated:' || n.id, 'not_applicable',
                    n.ncp_source, n.source_filename, n.content_hash, n.ncp_index,
                    n.created_by, n.status, n.model_name, n.created_at,
                    n.finalized_at
                ) RETURNING id INTO new_note_id;
                INSERT INTO ncp_clinical_note_map VALUES (n.id, new_note_id);
            END LOOP;
        END $$
        """,
    )

    op.rename_table(
        "person_nutrition_care_process_embeddings",
        "person_nutrition_clinical_note_embeddings",
    )
    op.add_column(
        "person_nutrition_clinical_note_embeddings",
        sa.Column("person_clinical_note_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "person_nutrition_clinical_note_embeddings",
        sa.Column(
            "type",
            sa.Enum(
                "Nutrition/Dietary",
                "Dietician",
                name="nutrition_clinical_note_type",
                native_enum=False,
                create_constraint=False,
            ),
            nullable=True,
        ),
    )
    op.execute(
        """
        UPDATE person_nutrition_clinical_note_embeddings e
        SET person_clinical_note_id = m.clinical_note_id,
            type = CASE
                WHEN lower(c.note_type) IN ('dietician', 'dietician progress note',
                    'dietitian', 'dietitian progress note') THEN 'Dietician'
                WHEN lower(c.note_type) IN ('nutrition/dietary',
                    'nutrition/dietary note') THEN 'Nutrition/Dietary'
                WHEN c.ncp_source = 'generated' THEN 'Nutrition/Dietary'
            END
        FROM ncp_clinical_note_map m
        JOIN person_clinical_note c ON c.id = m.clinical_note_id
        WHERE e.person_nutrition_care_process_id = m.old_ncp_id
        """,
    )
    op.execute(
        "DELETE FROM person_nutrition_clinical_note_embeddings WHERE type IS NULL",
    )
    op.drop_column(
        "person_nutrition_clinical_note_embeddings",
        "person_nutrition_care_process_id",
    )
    op.alter_column(
        "person_nutrition_clinical_note_embeddings",
        "person_clinical_note_id",
        nullable=False,
    )
    op.alter_column(
        "person_nutrition_clinical_note_embeddings",
        "type",
        nullable=False,
    )
    op.create_check_constraint(
        "nutrition_clinical_note_type",
        "person_nutrition_clinical_note_embeddings",
        "type IN ('Nutrition/Dietary', 'Dietician')",
    )
    op.create_foreign_key(
        "fk_nutrition_embedding_clinical_note",
        "person_nutrition_clinical_note_embeddings",
        "person_clinical_note",
        ["person_clinical_note_id"],
        ["id"],
    )
    _rename_index(
        "ix_person_nutrition_care_process_embeddings_vector_hnsw",
        "ix_person_nutrition_clinical_note_embeddings_vector_hnsw",
    )
    op.create_index(
        "uq_nutrition_clinical_note_embedding_note_id",
        "person_nutrition_clinical_note_embeddings",
        ["person_clinical_note_id"],
        unique=True,
    )
    op.create_index(
        "ix_person_nutrition_clinical_note_embeddings_type",
        "person_nutrition_clinical_note_embeddings",
        ["type"],
    )
    op.execute(
        "ALTER SEQUENCE IF EXISTS person_nutrition_care_process_embeddings_id_seq "
        "RENAME TO person_nutrition_clinical_note_embeddings_id_seq",
    )

    op.drop_table("person_nutrition_care_process")
    op.execute(
        "UPDATE person_clinical_note SET created_at = note_date "
        "WHERE created_at IS NULL",
    )
    op.alter_column("person_clinical_note", "created_at", nullable=False)
    op.create_check_constraint(
        "nutrition_care_process_source",
        "person_clinical_note",
        "ncp_source IN ('generated', 'imported')",
    )
    op.create_check_constraint(
        "ck_person_clinical_note_ncp_metadata",
        "person_clinical_note",
        "(ncp_source IS NULL AND status IS NULL AND content_hash IS NULL) OR "
        "(ncp_source IS NOT NULL AND status IS NOT NULL AND content_hash IS NOT NULL)",
    )
    op.create_unique_constraint(
        "uq_person_clinical_note_person_content_hash",
        "person_clinical_note",
        ["person_id", "content_hash"],
    )
    for column in (
        "ncp_source",
        "content_hash",
        "created_by",
        "status",
        "created_at",
    ):
        op.create_index(
            f"ix_person_clinical_note_{column}",
            "person_clinical_note",
            [column],
        )


def downgrade() -> None:
    """Restore separate progress-note and NCP tables."""
    op.drop_constraint(
        "ck_person_clinical_note_ncp_metadata",
        "person_clinical_note",
        type_="check",
    )
    op.drop_constraint(
        "nutrition_care_process_source",
        "person_clinical_note",
        type_="check",
    )
    op.create_table(
        "person_nutrition_care_process",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("person_id", sa.Integer(), nullable=False),
        sa.Column("source_progress_note_id", sa.Integer(), nullable=True),
        sa.Column("content", sa.String(), nullable=False),
        sa.Column(
            "ncp_source",
            sa.Enum(
                "generated",
                "imported",
                name="nutrition_care_process_source",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("source_filename", sa.String(), nullable=True),
        sa.Column("content_hash", sa.String(), nullable=False),
        sa.Column("ncp_index", sa.Integer(), nullable=False),
        sa.Column("ncp_date", sa.Date(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(
                "draft",
                "finalized",
                "discarded",
                name="nutrition_care_process_status",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("model_name", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("finalized_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["person_id"], ["person.id"]),
        sa.ForeignKeyConstraint(
            ["source_progress_note_id"],
            ["person_clinical_note.id"],
        ),
        sa.UniqueConstraint("person_id", "content_hash"),
    )
    op.execute(
        """
        INSERT INTO person_nutrition_care_process (
            id, person_id, source_progress_note_id, content, ncp_source,
            source_filename, content_hash, ncp_index, ncp_date, created_by,
            status, model_name, created_at, finalized_at
        )
        SELECT id, person_id,
               CASE WHEN ncp_source = 'imported' THEN id END,
               note_text, ncp_source, source_filename, content_hash,
               COALESCE(ncp_index, 0), note_date::date, created_by,
               status, model_name, created_at, finalized_at
        FROM person_clinical_note
        WHERE ncp_source IS NOT NULL
        """,
    )
    op.execute(
        "SELECT setval(pg_get_serial_sequence('person_nutrition_care_process', 'id'), "
        "COALESCE((SELECT MAX(id) FROM person_nutrition_care_process), 1))",
    )
    for column in (
        "ncp_date",
        "ncp_source",
        "content_hash",
        "created_at",
        "created_by",
        "person_id",
        "source_progress_note_id",
        "status",
    ):
        op.create_index(
            f"ix_person_nutrition_care_process_{column}",
            "person_nutrition_care_process",
            [column],
            unique=column == "source_progress_note_id",
        )

    op.add_column(
        "person_nutrition_clinical_note_embeddings",
        sa.Column("person_nutrition_care_process_id", sa.Integer(), nullable=True),
    )
    op.execute(
        "UPDATE person_nutrition_clinical_note_embeddings "
        "SET person_nutrition_care_process_id = person_clinical_note_id",
    )
    op.drop_constraint(
        "fk_nutrition_embedding_clinical_note",
        "person_nutrition_clinical_note_embeddings",
        type_="foreignkey",
    )
    op.drop_constraint(
        "nutrition_clinical_note_type",
        "person_nutrition_clinical_note_embeddings",
        type_="check",
    )
    op.drop_index(
        "uq_nutrition_clinical_note_embedding_note_id",
        table_name="person_nutrition_clinical_note_embeddings",
    )
    op.drop_index(
        "ix_person_nutrition_clinical_note_embeddings_type",
        table_name="person_nutrition_clinical_note_embeddings",
    )
    op.drop_column("person_nutrition_clinical_note_embeddings", "type")
    op.drop_column(
        "person_nutrition_clinical_note_embeddings",
        "person_clinical_note_id",
    )
    op.alter_column(
        "person_nutrition_clinical_note_embeddings",
        "person_nutrition_care_process_id",
        nullable=False,
    )
    op.create_foreign_key(
        "fk_ncp_embedding_ncp",
        "person_nutrition_clinical_note_embeddings",
        "person_nutrition_care_process",
        ["person_nutrition_care_process_id"],
        ["id"],
    )
    op.create_index(
        "uq_ncp_embedding_ncp_id",
        "person_nutrition_clinical_note_embeddings",
        ["person_nutrition_care_process_id"],
        unique=True,
    )
    _rename_index(
        "ix_person_nutrition_clinical_note_embeddings_vector_hnsw",
        "ix_person_nutrition_care_process_embeddings_vector_hnsw",
    )
    op.rename_table(
        "person_nutrition_clinical_note_embeddings",
        "person_nutrition_care_process_embeddings",
    )
    op.execute(
        "ALTER SEQUENCE IF EXISTS person_nutrition_clinical_note_embeddings_id_seq "
        "RENAME TO person_nutrition_care_process_embeddings_id_seq",
    )

    op.execute(
        "DELETE FROM person_clinical_note WHERE ncp_source = 'generated'",
    )
    op.drop_constraint(
        "uq_person_clinical_note_person_content_hash",
        "person_clinical_note",
        type_="unique",
    )
    for column in (
        "ncp_source",
        "content_hash",
        "created_by",
        "status",
        "created_at",
    ):
        op.drop_index(
            f"ix_person_clinical_note_{column}",
            table_name="person_clinical_note",
        )
    for column in (
        "finalized_at",
        "created_at",
        "model_name",
        "status",
        "created_by",
        "ncp_index",
        "content_hash",
        "source_filename",
        "ncp_source",
    ):
        op.drop_column("person_clinical_note", column)

    op.alter_column(
        "extracted_fact",
        "clinical_note_id",
        new_column_name="progress_note_id",
    )
    _rename_index(
        "ix_extracted_fact_clinical_note_id",
        "ix_extracted_fact_progress_note_id",
    )
    op.rename_table("person_clinical_note", "person_progress_note")
    for suffix in (
        "extraction_status",
        "note_date",
        "note_key",
        "person_id",
        "source_id",
    ):
        _rename_index(
            f"ix_person_clinical_note_{suffix}",
            f"ix_person_progress_note_{suffix}",
        )
    op.execute(
        "ALTER SEQUENCE IF EXISTS person_clinical_note_id_seq "
        "RENAME TO person_progress_note_id_seq",
    )
