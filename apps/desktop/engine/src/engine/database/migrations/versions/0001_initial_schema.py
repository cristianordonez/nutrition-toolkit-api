"""Create the initial relational desktop schema.

Revision ID: 0001
Revises: None
Create Date: 2026-09-27 15:11:59.731352
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:  # noqa: PLR0915 - frozen initial schema
    """Apply the migration."""
    op.create_table(
        "enteral_formula",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("brand", sa.String(), nullable=False),
        sa.Column("brand_owner", sa.String(), nullable=False),
        sa.Column(
            "package_type",
            sa.Enum("READY_TO_HANG", "CARTON", "BOTTLE", "CAN", name="packagetype"),
            nullable=False,
        ),
        sa.Column("serving_size", sa.Float(), nullable=False),
        sa.Column("serving_unit", sa.String(), nullable=False),
        sa.Column(
            "liquid_consistency",
            sa.Enum(
                "THIN",
                "SLIGHTLY_THICK",
                "MILDLY_THICK",
                "MODERATELY_THICK",
                "EXTREMELY_THICK",
                name="liquidconsistency",
            ),
            nullable=False,
        ),
        sa.Column("catalog_version", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("enteral_formula", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_enteral_formula_brand"),
            ["brand"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_enteral_formula_catalog_version"),
            ["catalog_version"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_enteral_formula_name"),
            ["name"],
            unique=True,
        )
        batch_op.create_index(
            batch_op.f("ix_enteral_formula_package_type"),
            ["package_type"],
            unique=False,
        )

    op.create_table(
        "facility",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("facility_identifier", sa.String(), nullable=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("normalized_name", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("facility", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_facility_facility_identifier"),
            ["facility_identifier"],
            unique=True,
        )
        batch_op.create_index(
            batch_op.f("ix_facility_normalized_name"),
            ["normalized_name"],
            unique=True,
        )

    op.create_table(
        "knowledge",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column(
            "knowledge_type",
            sa.Enum("DIET_MANUAL", "NUTRITION_CARE_MANUAL", name="knowledgetype"),
            nullable=False,
        ),
        sa.Column("file_hash", sa.String(), nullable=False),
        sa.Column("synced_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("knowledge", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_knowledge_file_hash"),
            ["file_hash"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_knowledge_knowledge_type"),
            ["knowledge_type"],
            unique=False,
        )

    op.create_table(
        "settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("full_name", sa.String(), nullable=True),
        sa.Column("credentials", sa.String(), nullable=True),
        sa.Column("dark_mode", sa.Boolean(), nullable=True),
        sa.Column("use_cloud_model", sa.Boolean(), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_settings_singleton"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "document",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("facility_id", sa.Integer(), nullable=True),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("media_type", sa.String(), nullable=False),
        sa.Column("checksum", sa.String(), nullable=False),
        sa.Column("storage_uri", sa.String(), nullable=True),
        sa.Column("byte_size", sa.Integer(), nullable=True),
        sa.Column("source_observed_at", sa.DateTime(), nullable=True),
        sa.Column("document_type", sa.String(), nullable=False),
        sa.Column("document_metadata", sa.JSON(), nullable=False),
        sa.Column("imported_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["facility_id"], ["facility.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("document", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_document_checksum"),
            ["checksum"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_document_document_type"),
            ["document_type"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_document_facility_id"),
            ["facility_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_document_media_type"),
            ["media_type"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_document_source_observed_at"),
            ["source_observed_at"],
            unique=False,
        )
        batch_op.create_index(
            "uq_document_facility_checksum",
            ["facility_id", "checksum"],
            unique=True,
            sqlite_where=sa.text("facility_id IS NOT NULL"),
        )
        batch_op.create_index(
            "uq_document_unscoped_checksum",
            ["checksum"],
            unique=True,
            sqlite_where=sa.text("facility_id IS NULL"),
        )

    op.create_table(
        "enteral_formula_nutrient",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("formula_id", sa.Integer(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("unit_name", sa.String(), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(
            ["formula_id"],
            ["enteral_formula.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("enteral_formula_nutrient", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_enteral_formula_nutrient_formula_id"),
            ["formula_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_enteral_formula_nutrient_number"),
            ["number"],
            unique=False,
        )

    op.create_table(
        "knowledge_chunk",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("knowledge_id", sa.Integer(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.String(), nullable=False),
        sa.Column("section_title", sa.String(), nullable=True),
        sa.Column("source_page_start", sa.Integer(), nullable=True),
        sa.Column("source_page_end", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["knowledge_id"],
            ["knowledge.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("knowledge_id", "chunk_index"),
    )
    with op.batch_alter_table("knowledge_chunk", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_knowledge_chunk_knowledge_id"),
            ["knowledge_id"],
            unique=False,
        )

    op.create_table(
        "person",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("facility_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("first_name", sa.String(), nullable=False),
        sa.Column("last_name", sa.String(), nullable=False),
        sa.Column("normalized_first_name", sa.String(), nullable=False),
        sa.Column("normalized_last_name", sa.String(), nullable=False),
        sa.Column("date_of_birth", sa.Date(), nullable=True),
        sa.Column("person_identifier", sa.String(), nullable=True),
        sa.Column("sex", sa.String(), nullable=True),
        sa.Column("height_in", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["facility_id"], ["facility.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("person", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_person_facility_id"),
            ["facility_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_person_normalized_first_name"),
            ["normalized_first_name"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_person_normalized_last_name"),
            ["normalized_last_name"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_person_person_identifier"),
            ["person_identifier"],
            unique=False,
        )
        batch_op.create_index(
            "uq_person_facility_identifier",
            ["facility_id", "person_identifier"],
            unique=True,
            sqlite_where=sa.text(
                "facility_id IS NOT NULL AND person_identifier IS NOT NULL",
            ),
        )
        batch_op.create_index(
            "uq_person_facility_natural_identity",
            [
                "facility_id",
                "normalized_first_name",
                "normalized_last_name",
                "date_of_birth",
            ],
            unique=True,
            sqlite_where=sa.text(
                "facility_id IS NOT NULL AND date_of_birth IS NOT NULL",
            ),
        )
        batch_op.create_index(
            "uq_person_unscoped_identifier",
            ["person_identifier"],
            unique=True,
            sqlite_where=sa.text(
                "facility_id IS NULL AND person_identifier IS NOT NULL",
            ),
        )
        batch_op.create_index(
            "uq_person_unscoped_natural_identity",
            ["normalized_first_name", "normalized_last_name", "date_of_birth"],
            unique=True,
            sqlite_where=sa.text("facility_id IS NULL AND date_of_birth IS NOT NULL"),
        )

    op.create_table(
        "clinical_source",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=True),
        sa.Column("person_id", sa.Integer(), nullable=True),
        sa.Column(
            "source_kind",
            sa.Enum(
                "progress_note",
                "report_section",
                "order_entry",
                "lab_section",
                "wound_entry",
                "text_block",
                "pasted_text",
                "api_record",
                "manual_entry",
                "application",
                "legacy",
                name="clinical_source_kind",
            ),
            nullable=False,
        ),
        sa.Column("source_key", sa.String(length=64), nullable=False),
        sa.Column("content", sa.String(), nullable=True),
        sa.Column("raw_content", sa.String(), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("title", sa.String(), nullable=True),
        sa.Column("note_type", sa.String(), nullable=True),
        sa.Column("author", sa.String(), nullable=True),
        sa.Column("effective_at", sa.DateTime(), nullable=True),
        sa.Column("page_start", sa.Integer(), nullable=True),
        sa.Column("page_end", sa.Integer(), nullable=True),
        sa.Column("source_section", sa.String(), nullable=True),
        sa.Column("locator", sa.JSON(), nullable=False),
        sa.Column("source_system", sa.String(), nullable=True),
        sa.Column("source_record_type", sa.String(), nullable=True),
        sa.Column("source_record_id", sa.String(), nullable=True),
        sa.Column("source_record_version", sa.String(), nullable=True),
        sa.Column("source_document_id", sa.String(), nullable=True),
        sa.Column("source_endpoint", sa.String(), nullable=True),
        sa.Column(
            "source_authority",
            sa.Enum(
                "authoritative_snapshot",
                "structured_record",
                "clinical_document",
                "historical_document",
                "unknown",
                name="source_authority",
            ),
            nullable=False,
        ),
        sa.Column(
            "extraction_status",
            sa.Enum(
                "pending",
                "extracted",
                "skipped",
                "failed",
                "not_applicable",
                name="extraction_status",
            ),
            nullable=False,
        ),
        sa.Column("source_metadata", sa.JSON(), nullable=False),
        sa.Column("received_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["document.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["person_id"], ["person.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("clinical_source", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_clinical_source_content_hash"),
            ["content_hash"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_clinical_source_document_id"),
            ["document_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_clinical_source_effective_at"),
            ["effective_at"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_clinical_source_extraction_status"),
            ["extraction_status"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_clinical_source_note_type"),
            ["note_type"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_clinical_source_person_id"),
            ["person_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_clinical_source_received_at"),
            ["received_at"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_clinical_source_source_authority"),
            ["source_authority"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_clinical_source_source_document_id"),
            ["source_document_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_clinical_source_source_key"),
            ["source_key"],
            unique=True,
        )
        batch_op.create_index(
            batch_op.f("ix_clinical_source_source_kind"),
            ["source_kind"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_clinical_source_source_record_id"),
            ["source_record_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_clinical_source_source_record_type"),
            ["source_record_type"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_clinical_source_source_system"),
            ["source_system"],
            unique=False,
        )

    op.create_table(
        "ncp_note",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=True),
        sa.Column("facility_id", sa.Integer(), nullable=True),
        sa.Column(
            "note_type",
            sa.Enum(
                "annual",
                "quarterly",
                "admission",
                "readmission",
                "payer_change",
                "follow_up",
                "significant_change",
                "wound",
                "high_risk",
                name="ncp_note_type",
            ),
            nullable=False,
        ),
        sa.Column("content", sa.String(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("example", "draft", "finalized", name="ncp_note_status"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("finalized_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "status != 'finalized' OR finalized_at IS NOT NULL",
            name="ck_ncp_note_finalized_at",
        ),
        sa.ForeignKeyConstraint(["facility_id"], ["facility.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["person_id"], ["person.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("ncp_note", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_ncp_note_created_at"),
            ["created_at"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_ncp_note_facility_id"),
            ["facility_id"],
            unique=False,
        )
        batch_op.create_index(
            "ix_ncp_note_facility_status_type",
            ["facility_id", "status", "note_type"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_ncp_note_finalized_at"),
            ["finalized_at"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_ncp_note_note_type"),
            ["note_type"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_ncp_note_person_id"),
            ["person_id"],
            unique=False,
        )
        batch_op.create_index(
            "ix_ncp_note_person_status_finalized",
            ["person_id", "status", "finalized_at"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_ncp_note_status"),
            ["status"],
            unique=False,
        )

    op.create_table(
        "clinical_fact",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=False),
        sa.Column("clinical_source_id", sa.Integer(), nullable=True),
        sa.Column("fact_type", sa.String(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("payload_schema_version", sa.Integer(), nullable=False),
        sa.Column("effective_at", sa.DateTime(), nullable=True),
        sa.Column("observed_at", sa.DateTime(), nullable=True),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        sa.Column("lifecycle_status", sa.String(), nullable=True),
        sa.Column("concept_key", sa.String(), nullable=True),
        sa.Column("identity_hash", sa.String(length=64), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "extraction_method",
            sa.Enum(
                "DETERMINISTIC",
                "AI",
                "API",
                "IMPORT",
                "MANUAL",
                "CALCULATED",
                "APPLICATION",
                name="extractionmethod",
            ),
            nullable=False,
        ),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("confidence_reason", sa.String(), nullable=True),
        sa.Column("model_name", sa.String(), nullable=True),
        sa.Column("extractor_name", sa.String(), nullable=True),
        sa.Column("extractor_version", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_clinical_fact_confidence",
        ),
        sa.CheckConstraint(
            "payload_schema_version > 0",
            name="ck_clinical_fact_payload_version",
        ),
        sa.ForeignKeyConstraint(
            ["clinical_source_id"],
            ["clinical_source.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["person_id"], ["person.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "clinical_source_id",
            "fact_type",
            "identity_hash",
            name="uq_clinical_fact_source_identity",
        ),
    )
    with op.batch_alter_table("clinical_fact", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_clinical_fact_clinical_source_id"),
            ["clinical_source_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_clinical_fact_concept_key"),
            ["concept_key"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_clinical_fact_content_hash"),
            ["content_hash"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_clinical_fact_created_at"),
            ["created_at"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_clinical_fact_effective_at"),
            ["effective_at"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_clinical_fact_ended_at"),
            ["ended_at"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_clinical_fact_extraction_method"),
            ["extraction_method"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_clinical_fact_fact_type"),
            ["fact_type"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_clinical_fact_identity_hash"),
            ["identity_hash"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_clinical_fact_lifecycle_status"),
            ["lifecycle_status"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_clinical_fact_observed_at"),
            ["observed_at"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_clinical_fact_person_id"),
            ["person_id"],
            unique=False,
        )
        batch_op.create_index(
            "ix_clinical_fact_person_type_concept_effective",
            ["person_id", "fact_type", "concept_key", "effective_at"],
            unique=False,
        )
        batch_op.create_index(
            "ix_clinical_fact_person_type_effective",
            ["person_id", "fact_type", "effective_at", "id"],
            unique=False,
        )
        batch_op.create_index(
            "ix_clinical_fact_person_type_status_effective",
            ["person_id", "fact_type", "lifecycle_status", "effective_at"],
            unique=False,
        )
        batch_op.create_index(
            "uq_clinical_fact_without_source_identity",
            ["person_id", "fact_type", "identity_hash"],
            unique=True,
            sqlite_where=sa.text("clinical_source_id IS NULL"),
        )


def downgrade() -> None:
    """Remove relational tables in reverse foreign-key order."""
    for name in (
        "clinical_fact",
        "ncp_note",
        "clinical_source",
        "person",
        "knowledge_chunk",
        "enteral_formula_nutrient",
        "document",
        "settings",
        "knowledge",
        "facility",
        "enteral_formula",
    ):
        op.drop_table(name)
