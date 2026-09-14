"""Rename complete assessment-note storage to Nutrition Care Process storage.

Revision ID: 20260912_0002
Revises: 20260912_0001
Create Date: 2026-09-12
"""

from __future__ import annotations

import typing

from alembic import op

if typing.TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "20260912_0002"
down_revision: str | Sequence[str] | None = "20260912_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_UPGRADE_RENAMES = (
    (
        "ix_person_assessment_assessment_date",
        "ix_person_nutrition_care_process_ncp_date",
    ),
    (
        "ix_person_assessment_assessment_source",
        "ix_person_nutrition_care_process_ncp_source",
    ),
    (
        "ix_person_assessment_content_hash",
        "ix_person_nutrition_care_process_content_hash",
    ),
    ("ix_person_assessment_created_at", "ix_person_nutrition_care_process_created_at"),
    ("ix_person_assessment_created_by", "ix_person_nutrition_care_process_created_by"),
    ("ix_person_assessment_person_id", "ix_person_nutrition_care_process_person_id"),
    (
        "ix_person_assessment_source_progress_note_id",
        "ix_person_nutrition_care_process_source_progress_note_id",
    ),
    ("ix_person_assessment_status", "ix_person_nutrition_care_process_status"),
    (
        "ix_person_assessment_embeddings_person_assessment_id",
        "uq_ncp_embedding_ncp_id",
    ),
    (
        "ix_person_assessment_embeddings_embedding_vector_hnsw",
        "ix_person_nutrition_care_process_embeddings_vector_hnsw",
    ),
)


def _rename_indexes(renames: tuple[tuple[str, str], ...]) -> None:
    for old_name, new_name in renames:
        op.execute(f'ALTER INDEX IF EXISTS "{old_name}" RENAME TO "{new_name}"')


def upgrade() -> None:
    """Rename assessment-era persistence names without replacing stored data."""
    op.rename_table("person_assessment", "person_nutrition_care_process")
    op.alter_column(
        "person_nutrition_care_process",
        "assessment_source",
        new_column_name="ncp_source",
    )
    op.alter_column(
        "person_nutrition_care_process",
        "assessment_index",
        new_column_name="ncp_index",
    )
    op.alter_column(
        "person_nutrition_care_process",
        "assessment_date",
        new_column_name="ncp_date",
    )
    op.rename_table(
        "person_assessment_embeddings",
        "person_nutrition_care_process_embeddings",
    )
    op.alter_column(
        "person_nutrition_care_process_embeddings",
        "person_assessment_id",
        new_column_name="person_nutrition_care_process_id",
    )

    _rename_indexes(_UPGRADE_RENAMES)
    op.execute(
        "ALTER SEQUENCE IF EXISTS person_assessment_id_seq "
        "RENAME TO person_nutrition_care_process_id_seq",
    )
    op.execute(
        "ALTER SEQUENCE IF EXISTS person_assessment_embeddings_id_seq "
        "RENAME TO person_nutrition_care_process_embeddings_id_seq",
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'status_type')
               AND NOT EXISTS (
                   SELECT 1 FROM pg_type
                   WHERE typname = 'nutrition_care_process_status'
               ) THEN
                ALTER TYPE status_type RENAME TO nutrition_care_process_status;
            END IF;
        END $$
        """,
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'assessment_source'
                  AND conrelid = 'person_nutrition_care_process'::regclass
            ) THEN
                ALTER TABLE person_nutrition_care_process
                    RENAME CONSTRAINT assessment_source
                    TO nutrition_care_process_source;
            END IF;
        END $$
        """,
    )
    op.execute(
        """
        DO $$
        DECLARE
            old_permission RECORD;
            target_name TEXT;
            target_id INTEGER;
        BEGIN
            FOR old_permission IN
                SELECT id, name FROM permission
                WHERE name IN ('assessments:read', 'assessments:write')
            LOOP
                target_name := CASE old_permission.name
                    WHEN 'assessments:read'
                        THEN 'nutrition-care-processes:read'
                    ELSE 'nutrition-care-processes:write'
                END;
                SELECT id INTO target_id
                FROM permission
                WHERE name = target_name;

                IF target_id IS NULL THEN
                    UPDATE permission
                    SET name = target_name
                    WHERE id = old_permission.id;
                ELSE
                    INSERT INTO api_key_permission (api_key_id, permission_id)
                    SELECT api_key_id, target_id
                    FROM api_key_permission
                    WHERE permission_id = old_permission.id
                    ON CONFLICT DO NOTHING;
                    DELETE FROM api_key_permission
                    WHERE permission_id = old_permission.id;
                    DELETE FROM permission WHERE id = old_permission.id;
                END IF;
            END LOOP;
        END $$
        """,
    )


def downgrade() -> None:
    """Restore the former assessment-era persistence names."""
    op.execute(
        """
        DO $$
        DECLARE
            old_permission RECORD;
            target_name TEXT;
            target_id INTEGER;
        BEGIN
            FOR old_permission IN
                SELECT id, name FROM permission
                WHERE name IN (
                    'nutrition-care-processes:read',
                    'nutrition-care-processes:write'
                )
            LOOP
                target_name := CASE old_permission.name
                    WHEN 'nutrition-care-processes:read' THEN 'assessments:read'
                    ELSE 'assessments:write'
                END;
                SELECT id INTO target_id
                FROM permission
                WHERE name = target_name;

                IF target_id IS NULL THEN
                    UPDATE permission
                    SET name = target_name
                    WHERE id = old_permission.id;
                ELSE
                    INSERT INTO api_key_permission (api_key_id, permission_id)
                    SELECT api_key_id, target_id
                    FROM api_key_permission
                    WHERE permission_id = old_permission.id
                    ON CONFLICT DO NOTHING;
                    DELETE FROM api_key_permission
                    WHERE permission_id = old_permission.id;
                    DELETE FROM permission WHERE id = old_permission.id;
                END IF;
            END LOOP;
        END $$
        """,
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'nutrition_care_process_source'
                  AND conrelid = 'person_nutrition_care_process'::regclass
            ) THEN
                ALTER TABLE person_nutrition_care_process
                    RENAME CONSTRAINT nutrition_care_process_source
                    TO assessment_source;
            END IF;
        END $$
        """,
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_type
                WHERE typname = 'nutrition_care_process_status'
            ) AND NOT EXISTS (
                SELECT 1 FROM pg_type WHERE typname = 'status_type'
            ) THEN
                ALTER TYPE nutrition_care_process_status RENAME TO status_type;
            END IF;
        END $$
        """,
    )
    op.execute(
        "ALTER SEQUENCE IF EXISTS person_nutrition_care_process_embeddings_id_seq "
        "RENAME TO person_assessment_embeddings_id_seq",
    )
    op.execute(
        "ALTER SEQUENCE IF EXISTS person_nutrition_care_process_id_seq "
        "RENAME TO person_assessment_id_seq",
    )
    _rename_indexes(
        tuple((new_name, old_name) for old_name, new_name in _UPGRADE_RENAMES),
    )

    op.alter_column(
        "person_nutrition_care_process_embeddings",
        "person_nutrition_care_process_id",
        new_column_name="person_assessment_id",
    )
    op.rename_table(
        "person_nutrition_care_process_embeddings",
        "person_assessment_embeddings",
    )
    op.alter_column(
        "person_nutrition_care_process",
        "ncp_date",
        new_column_name="assessment_date",
    )
    op.alter_column(
        "person_nutrition_care_process",
        "ncp_index",
        new_column_name="assessment_index",
    )
    op.alter_column(
        "person_nutrition_care_process",
        "ncp_source",
        new_column_name="assessment_source",
    )
    op.rename_table("person_nutrition_care_process", "person_assessment")
