"""Create the complete legacy schema required by subsequent migrations.

Revision ID: 20260912_0000
Revises:
Create Date: 2026-09-12
"""

# This immutable baseline intentionally keeps explicit generated schema operations.
# ruff: noqa: E501, PLR0915

from __future__ import annotations

import typing

import pgvector.sqlalchemy
import sqlalchemy as sa
import sqlmodel
from sqlalchemy.dialects import postgresql

from alembic import op

if typing.TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "20260912_0000"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NATIVE_ENUMS = (
    postgresql.ENUM(
        "VERY_POOR",
        "POOR",
        "FAIR",
        "GOOD",
        "EXCELLENT",
        "UNKNOWN",
        name="appetitelevel",
    ),
    postgresql.ENUM("observation", "event", name="clinical_fact_type"),
    postgresql.ENUM(
        "ACTIVE",
        "INACTIVE",
        "HISTORICAL",
        "UNKNOWN",
        name="clinicalstatus",
    ),
    postgresql.ENUM(
        "NATURAL",
        "PARTIAL_DENTITION",
        "EDENTULOUS",
        "DENTURES",
        "UNKNOWN",
        name="dentitionstatus",
    ),
    postgresql.ENUM(
        "PRESENT",
        "ABSENT",
        "PARTIAL",
        "NOT_WORN",
        "UNAVAILABLE",
        "UNKNOWN",
        name="denturestatus",
    ),
    postgresql.ENUM(
        "HEMODIALYSIS",
        "PERITONEAL_DIALYSIS",
        "OTHER",
        "UNKNOWN",
        name="dialysistype",
    ),
    postgresql.ENUM("PDF", "CSV", "TEXT", "API", name="documentsourcetype"),
    postgresql.ENUM(
        "pending",
        "extracted",
        "skipped",
        "failed",
        name="extraction_status",
    ),
    postgresql.ENUM(
        "DETERMINISTIC",
        "AI",
        "API",
        "IMPORT",
        "MANUAL",
        name="extractionmethod",
    ),
    postgresql.ENUM("CONTINUOUS", "CYCLIC", "BOLUS", "UNKNOWN", name="feedingmethod"),
    postgresql.ENUM("USDA", "FATSECRET", "INTERNAL", name="foodcategorysource"),
    postgresql.ENUM(
        "PERSONAL",
        "CULTURAL",
        "RELIGIOUS",
        "ETHICAL",
        "OTHER",
        "UNKNOWN",
        name="foodpreferencereason",
    ),
    postgresql.ENUM(
        "FOOD",
        "BEVERAGE",
        "CUISINE",
        "MEAL_PATTERN",
        "DIETARY_PRACTICE",
        "OTHER",
        name="foodpreferencetype",
    ),
    postgresql.ENUM(
        "LIKES",
        "DISLIKES",
        "PREFERS",
        "AVOIDS",
        "REQUIRES",
        name="foodpreferencevalue",
    ),
    postgresql.ENUM(
        "USDA_BRANDED",
        "USDA_FNDDS",
        "USDA_FOUNDATION",
        "USDA_SR_LEGACY",
        "FATSECRET",
        "MANUFACTURER",
        "INTERNAL",
        name="foodsourcetype",
    ),
    postgresql.ENUM("FOOD", "ORAL_SUPPLEMENT", "ENTERAL_FORMULA", name="foodtype"),
    postgresql.ENUM(
        "NAUSEA",
        "VOMITING",
        "DIARRHEA",
        "CONSTIPATION",
        "ABDOMINAL_PAIN",
        "EARLY_SATIETY",
        "BLOATING",
        "REFLUX",
        "OTHER",
        name="gisymptom",
    ),
    postgresql.ENUM("API", "MANUAL", name="importmethod"),
    postgresql.ENUM(
        "INCLUDED",
        "PIGGYBACK",
        "NONE",
        "UNKNOWN",
        name="lipiddeliverytype",
    ),
    postgresql.ENUM(
        "THIN",
        "SLIGHTLY_THICK",
        "MILDLY_THICK",
        "MODERATELY_THICK",
        "EXTREMELY_THICK",
        name="liquidconsistency",
    ),
    postgresql.ENUM(
        "MACRONUTRIENT",
        "VITAMIN",
        "MINERAL",
        name="nutrientclassification",
    ),
    postgresql.ENUM(
        "WEIGHT_GAIN",
        "WEIGHT_MAINTENANCE",
        "WEIGHT_LOSS",
        "INCREASE_PROTEIN",
        "INCREASE_CALORIES",
        "INCREASE_FLUID",
        "FLUID_RESTRICTION",
        "IMPROVE_MEAL_INTAKE",
        "INCREASE_FIBER",
        "REDUCE_SODIUM",
        "OTHER",
        name="nutritiongoaltype",
    ),
    postgresql.ENUM("READY_TO_HANG", "CARTON", "BOTTLE", "CAN", name="packagetype"),
    postgresql.ENUM("CENTRAL", "PERIPHERAL", "UNKNOWN", name="parenteralaccessroute"),
    postgresql.ENUM(
        "STANDARD",
        "CONCENTRATED",
        "CUSTOM",
        "UNKNOWN",
        name="parenteralformulatype",
    ),
    postgresql.ENUM(
        "ACTIVE",
        "INACTIVE",
        "HISTORICAL",
        "UNKNOWN",
        name="parenteralnutritionstatus",
    ),
    postgresql.ENUM(
        "AUTHORITATIVE_SNAPSHOT",
        "STRUCTURED_RECORD",
        "CLINICAL_DOCUMENT",
        "HISTORICAL_DOCUMENT",
        "UNKNOWN",
        name="sourceauthority",
    ),
    postgresql.ENUM("draft", "finalized", "discarded", name="status_type"),
    postgresql.ENUM(
        "ROUTINE",
        "PRE_DIALYSIS",
        "POST_DIALYSIS",
        "DRY_WEIGHT",
        "TARGET_WEIGHT",
        "UNKNOWN",
        name="weightcontext",
    ),
)


def upgrade() -> None:
    """Create a complete schema on an empty PostgreSQL database."""
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    bind = op.get_bind()
    for enum_type in _NATIVE_ENUMS:
        enum_type.create(bind, checkfirst=False)
    op.create_table(
        "api_key",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("api_key_hash", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "facility",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "facility_identifier",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=True,
        ),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column(
            "normalized_name",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_facility_facility_identifier"),
        "facility",
        ["facility_identifier"],
        unique=True,
    )
    op.create_index(
        op.f("ix_facility_normalized_name"),
        "facility",
        ["normalized_name"],
        unique=True,
    )
    op.create_table(
        "food_category",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column(
            "source",
            postgresql.ENUM(
                "USDA",
                "FATSECRET",
                "INTERNAL",
                name="foodcategorysource",
                create_type=False,
            ),
            nullable=True,
        ),
        sa.Column("external_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "food_sync_state",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "source",
            postgresql.ENUM(
                "USDA_BRANDED",
                "USDA_FNDDS",
                "USDA_FOUNDATION",
                "USDA_SR_LEGACY",
                "FATSECRET",
                "MANUFACTURER",
                "INTERNAL",
                name="foodsourcetype",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("last_completed_page", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_food_sync_state_source"),
        "food_sync_state",
        ["source"],
        unique=True,
    )
    op.create_table(
        "knowledge",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("filename", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column(
            "knowledge_type",
            sa.Enum(
                "diet-manual",
                "nutrition-care-manual",
                name="knowledge_type",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("file_hash", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("synced_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_knowledge_file_hash"),
        "knowledge",
        ["file_hash"],
        unique=False,
    )
    op.create_index(
        op.f("ix_knowledge_knowledge_type"),
        "knowledge",
        ["knowledge_type"],
        unique=False,
    )
    op.create_table(
        "nutrient",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("unit_name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column(
            "classification",
            postgresql.ENUM(
                "MACRONUTRIENT",
                "VITAMIN",
                "MINERAL",
                name="nutrientclassification",
                create_type=False,
            ),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "permission",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_permission_name"), "permission", ["name"], unique=True)
    op.create_table(
        "user",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("email", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_user_email"), "user", ["email"], unique=True)
    op.create_table(
        "api_key_permission",
        sa.Column("api_key_id", sa.Integer(), nullable=False),
        sa.Column("permission_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["api_key_id"],
            ["api_key.id"],
        ),
        sa.ForeignKeyConstraint(
            ["permission_id"],
            ["permission.id"],
        ),
        sa.PrimaryKeyConstraint("api_key_id", "permission_id"),
    )
    op.create_table(
        "document",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("filename", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("file_type", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("checksum", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("storage_uri", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("imported_at", sa.DateTime(), nullable=False),
        sa.Column("source_observed_at", sa.DateTime(), nullable=True),
        sa.Column("document_type", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("facility_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["facility_id"],
            ["facility.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_document_checksum"), "document", ["checksum"], unique=True)
    op.create_index(
        op.f("ix_document_document_type"),
        "document",
        ["document_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_document_facility_id"),
        "document",
        ["facility_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_document_file_type"),
        "document",
        ["file_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_document_source_observed_at"),
        "document",
        ["source_observed_at"],
        unique=False,
    )
    op.create_table(
        "food",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column(
            "food_type",
            postgresql.ENUM(
                "FOOD",
                "ORAL_SUPPLEMENT",
                "ENTERAL_FORMULA",
                name="foodtype",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "source_type",
            postgresql.ENUM(
                "USDA_BRANDED",
                "USDA_FNDDS",
                "USDA_FOUNDATION",
                "USDA_SR_LEGACY",
                "FATSECRET",
                "MANUFACTURER",
                "INTERNAL",
                name="foodsourcetype",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "import_method",
            postgresql.ENUM("API", "MANUAL", name="importmethod", create_type=False),
            nullable=False,
        ),
        sa.Column("source_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("brand", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("brand_owner", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("gtin_upc", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("ingredients", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("serving_size", sa.Float(), nullable=True),
        sa.Column("serving_unit", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column(
            "liquid_consistency",
            postgresql.ENUM(
                "THIN",
                "SLIGHTLY_THICK",
                "MILDLY_THICK",
                "MODERATELY_THICK",
                "EXTREMELY_THICK",
                name="liquidconsistency",
                create_type=False,
            ),
            nullable=True,
        ),
        sa.Column(
            "package_type",
            postgresql.ENUM(
                "READY_TO_HANG",
                "CARTON",
                "BOTTLE",
                "CAN",
                name="packagetype",
                create_type=False,
            ),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=True),
        sa.Column("source_published_at", sa.Date(), nullable=True),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["food_category.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_type", "source_id", name="uq_food_source"),
    )
    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("knowledge_id", sa.Integer(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("section_title", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("source_page_start", sa.Integer(), nullable=True),
        sa.Column("source_page_end", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "source_page_end IS NULL OR source_page_start IS NULL OR source_page_end >= source_page_start",
            name="ck_knowledge_chunks_source_page_range",
        ),
        sa.CheckConstraint(
            "source_page_start IS NULL OR source_page_start >= 1",
            name="ck_knowledge_chunks_source_page_start",
        ),
        sa.ForeignKeyConstraint(
            ["knowledge_id"],
            ["knowledge.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("knowledge_id", "chunk_index"),
    )
    op.create_index(
        op.f("ix_knowledge_chunks_knowledge_id"),
        "knowledge_chunks",
        ["knowledge_id"],
        unique=False,
    )
    op.create_table(
        "person",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("first_name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("last_name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column(
            "normalized_first_name",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=False,
        ),
        sa.Column(
            "normalized_last_name",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=False,
        ),
        sa.Column("date_of_birth", sa.Date(), nullable=True),
        sa.Column("facility_id", sa.Integer(), nullable=True),
        sa.Column(
            "person_identifier",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=True,
        ),
        sa.Column("sex", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("height_in", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["facility_id"],
            ["facility.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "normalized_first_name",
            "normalized_last_name",
            "date_of_birth",
            name="uq_person_natural_identity",
        ),
    )
    op.create_index(
        op.f("ix_person_facility_id"),
        "person",
        ["facility_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_normalized_first_name"),
        "person",
        ["normalized_first_name"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_normalized_last_name"),
        "person",
        ["normalized_last_name"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_person_identifier"),
        "person",
        ["person_identifier"],
        unique=False,
    )
    op.create_index(
        "uq_person_identifier_with_facility",
        "person",
        ["facility_id", "person_identifier"],
        unique=True,
        postgresql_where=sa.text(
            "facility_id IS NOT NULL AND person_identifier IS NOT NULL",
        ),
        sqlite_where=sa.text(
            "facility_id IS NOT NULL AND person_identifier IS NOT NULL",
        ),
    )
    op.create_index(
        "uq_person_identifier_without_facility",
        "person",
        ["person_identifier"],
        unique=True,
        postgresql_where=sa.text(
            "facility_id IS NULL AND person_identifier IS NOT NULL",
        ),
        sqlite_where=sa.text("facility_id IS NULL AND person_identifier IS NOT NULL"),
    )
    op.create_table(
        "user_hash",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("hash", sa.String(length=350), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_user_hash_user_id"),
        "user_hash",
        ["user_id"],
        unique=False,
    )
    op.create_table(
        "document_source",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column(
            "source_type",
            postgresql.ENUM(
                "PDF",
                "CSV",
                "TEXT",
                "API",
                name="documentsourcetype",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("source_page", sa.Integer(), nullable=True),
        sa.Column(
            "evidence_hash",
            sqlmodel.sql.sqltypes.AutoString(length=64),
            nullable=False,
        ),
        sa.Column("source_section", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("source_system", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column(
            "source_record_type",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=True,
        ),
        sa.Column(
            "source_record_id",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=True,
        ),
        sa.Column(
            "source_record_version",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=True,
        ),
        sa.Column(
            "source_document_id",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=True,
        ),
        sa.Column("source_endpoint", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column(
            "source_authority",
            postgresql.ENUM(
                "AUTHORITATIVE_SNAPSHOT",
                "STRUCTURED_RECORD",
                "CLINICAL_DOCUMENT",
                "HISTORICAL_DOCUMENT",
                "UNKNOWN",
                name="sourceauthority",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("received_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["document.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "source_page", "evidence_hash"),
    )
    op.create_index(
        op.f("ix_document_source_document_id"),
        "document_source",
        ["document_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_document_source_evidence_hash"),
        "document_source",
        ["evidence_hash"],
        unique=False,
    )
    op.create_index(
        op.f("ix_document_source_received_at"),
        "document_source",
        ["received_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_document_source_source_authority"),
        "document_source",
        ["source_authority"],
        unique=False,
    )
    op.create_index(
        op.f("ix_document_source_source_document_id"),
        "document_source",
        ["source_document_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_document_source_source_record_id"),
        "document_source",
        ["source_record_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_document_source_source_record_type"),
        "document_source",
        ["source_record_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_document_source_source_system"),
        "document_source",
        ["source_system"],
        unique=False,
    )
    op.create_index(
        op.f("ix_document_source_source_type"),
        "document_source",
        ["source_type"],
        unique=False,
    )
    op.create_table(
        "food_nutrient",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("food_id", sa.Integer(), nullable=False),
        sa.Column("nutrient_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(
            ["food_id"],
            ["food.id"],
        ),
        sa.ForeignKeyConstraint(
            ["nutrient_id"],
            ["nutrient.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "knowledge_chunks_embeddings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("knowledge_chunk_id", sa.Integer(), nullable=False),
        sa.Column(
            "embedding_vector",
            pgvector.sqlalchemy.VECTOR(dim=384).with_variant(sa.JSON(), "sqlite"),
            nullable=False,
        ),
        sa.Column("model_name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["knowledge_chunk_id"],
            ["knowledge_chunks.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_knowledge_chunks_embeddings_embedding_vector_hnsw",
        "knowledge_chunks_embeddings",
        ["embedding_vector"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_ops={"embedding_vector": "vector_cosine_ops"},
    )
    op.create_index(
        op.f("ix_knowledge_chunks_embeddings_knowledge_chunk_id"),
        "knowledge_chunks_embeddings",
        ["knowledge_chunk_id"],
        unique=False,
    )
    op.create_table(
        "person_progress_note",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=False),
        sa.Column("note_date", sa.DateTime(), nullable=False),
        sa.Column("note_type", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("author", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("note_text", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("raw_text", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("note_key", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column(
            "extraction_status",
            postgresql.ENUM(
                "pending",
                "extracted",
                "skipped",
                "failed",
                name="extraction_status",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("source_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["person_id"],
            ["person.id"],
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["document_source.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("person_id", "note_key"),
    )
    op.create_index(
        op.f("ix_person_progress_note_extraction_status"),
        "person_progress_note",
        ["extraction_status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_progress_note_note_date"),
        "person_progress_note",
        ["note_date"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_progress_note_note_key"),
        "person_progress_note",
        ["note_key"],
        unique=True,
    )
    op.create_index(
        op.f("ix_person_progress_note_person_id"),
        "person_progress_note",
        ["person_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_progress_note_source_id"),
        "person_progress_note",
        ["source_id"],
        unique=False,
    )
    op.create_table(
        "extracted_fact",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=True),
        sa.Column("facility_id", sa.Integer(), nullable=True),
        sa.Column("progress_note_id", sa.Integer(), nullable=True),
        sa.Column(
            "source_person_name",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=True,
        ),
        sa.Column(
            "source_person_identifier",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=True,
        ),
        sa.Column("facility_name", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column(
            "source_facility_identifier",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=True,
        ),
        sa.Column("source_id", sa.Integer(), nullable=True),
        sa.Column("source_page", sa.Integer(), nullable=True),
        sa.Column(
            "fact_key",
            sqlmodel.sql.sqltypes.AutoString(length=64),
            nullable=False,
        ),
        sa.Column("fact_type", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("observed_at", sa.DateTime(), nullable=True),
        sa.Column("effective_at", sa.DateTime(), nullable=True),
        sa.Column(
            "extraction_method",
            postgresql.ENUM(
                "DETERMINISTIC",
                "AI",
                "API",
                "IMPORT",
                "MANUAL",
                name="extractionmethod",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column(
            "confidence_reason",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=True,
        ),
        sa.Column("model_name", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("extractor_name", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column(
            "extractor_version",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=True,
        ),
        sa.Column("extracted_at", sa.DateTime(), nullable=False),
        sa.Column("transformed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["facility_id"],
            ["facility.id"],
        ),
        sa.ForeignKeyConstraint(
            ["person_id"],
            ["person.id"],
        ),
        sa.ForeignKeyConstraint(
            ["progress_note_id"],
            ["person_progress_note.id"],
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["document_source.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_id", "fact_key"),
    )
    op.create_index(
        op.f("ix_extracted_fact_effective_at"),
        "extracted_fact",
        ["effective_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_extracted_fact_extraction_method"),
        "extracted_fact",
        ["extraction_method"],
        unique=False,
    )
    op.create_index(
        op.f("ix_extracted_fact_facility_id"),
        "extracted_fact",
        ["facility_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_extracted_fact_fact_key"),
        "extracted_fact",
        ["fact_key"],
        unique=False,
    )
    op.create_index(
        op.f("ix_extracted_fact_fact_type"),
        "extracted_fact",
        ["fact_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_extracted_fact_observed_at"),
        "extracted_fact",
        ["observed_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_extracted_fact_person_id"),
        "extracted_fact",
        ["person_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_extracted_fact_progress_note_id"),
        "extracted_fact",
        ["progress_note_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_extracted_fact_source_facility_identifier"),
        "extracted_fact",
        ["source_facility_identifier"],
        unique=False,
    )
    op.create_index(
        op.f("ix_extracted_fact_source_id"),
        "extracted_fact",
        ["source_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_extracted_fact_source_page"),
        "extracted_fact",
        ["source_page"],
        unique=False,
    )
    op.create_index(
        op.f("ix_extracted_fact_source_person_identifier"),
        "extracted_fact",
        ["source_person_identifier"],
        unique=False,
    )
    op.create_table(
        "person_assessment",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=False),
        sa.Column("source_progress_note_id", sa.Integer(), nullable=True),
        sa.Column("content", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column(
            "assessment_source",
            sa.Enum(
                "generated",
                "imported",
                name="assessment_source",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("source_filename", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("content_hash", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("assessment_index", sa.Integer(), nullable=False),
        sa.Column("assessment_date", sa.Date(), nullable=False),
        sa.Column("created_by", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(
                "draft",
                "finalized",
                "discarded",
                name="status_type",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("model_name", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("finalized_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["person_id"],
            ["person.id"],
        ),
        sa.ForeignKeyConstraint(
            ["source_progress_note_id"],
            ["person_progress_note.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("person_id", "content_hash"),
    )
    op.create_index(
        op.f("ix_person_assessment_assessment_date"),
        "person_assessment",
        ["assessment_date"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_assessment_assessment_source"),
        "person_assessment",
        ["assessment_source"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_assessment_content_hash"),
        "person_assessment",
        ["content_hash"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_assessment_created_at"),
        "person_assessment",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_assessment_created_by"),
        "person_assessment",
        ["created_by"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_assessment_person_id"),
        "person_assessment",
        ["person_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_assessment_source_progress_note_id"),
        "person_assessment",
        ["source_progress_note_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_person_assessment_status"),
        "person_assessment",
        ["status"],
        unique=False,
    )
    op.create_table(
        "person_allergy",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=False),
        sa.Column("allergen", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("reaction", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("no_known_allergies", sa.Boolean(), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(
                "ACTIVE",
                "INACTIVE",
                "HISTORICAL",
                "UNKNOWN",
                name="clinicalstatus",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("observed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column(
            "state_key",
            sqlmodel.sql.sqltypes.AutoString(length=64),
            nullable=False,
        ),
        sa.Column("extracted_fact_id", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "(allergen IS NOT NULL AND no_known_allergies = false) OR (allergen IS NULL AND no_known_allergies = true)",
            name="ck_person_allergy_subject",
        ),
        sa.ForeignKeyConstraint(
            ["extracted_fact_id"],
            ["extracted_fact.id"],
        ),
        sa.ForeignKeyConstraint(
            ["person_id"],
            ["person.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("person_id", "state_key"),
    )
    op.create_index(
        op.f("ix_person_allergy_allergen"),
        "person_allergy",
        ["allergen"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_allergy_created_at"),
        "person_allergy",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_allergy_extracted_fact_id"),
        "person_allergy",
        ["extracted_fact_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_person_allergy_observed_at"),
        "person_allergy",
        ["observed_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_allergy_person_id"),
        "person_allergy",
        ["person_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_allergy_state_key"),
        "person_allergy",
        ["state_key"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_allergy_status"),
        "person_allergy",
        ["status"],
        unique=False,
    )
    op.create_table(
        "person_appetite_observation",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=False),
        sa.Column(
            "appetite",
            postgresql.ENUM(
                "VERY_POOR",
                "POOR",
                "FAIR",
                "GOOD",
                "EXCELLENT",
                "UNKNOWN",
                name="appetitelevel",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("notes", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("observed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column(
            "observation_key",
            sqlmodel.sql.sqltypes.AutoString(length=64),
            nullable=False,
        ),
        sa.Column("extracted_fact_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["extracted_fact_id"],
            ["extracted_fact.id"],
        ),
        sa.ForeignKeyConstraint(
            ["person_id"],
            ["person.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_person_appetite_observation_appetite"),
        "person_appetite_observation",
        ["appetite"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_appetite_observation_created_at"),
        "person_appetite_observation",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_appetite_observation_extracted_fact_id"),
        "person_appetite_observation",
        ["extracted_fact_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_person_appetite_observation_observation_key"),
        "person_appetite_observation",
        ["observation_key"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_appetite_observation_observed_at"),
        "person_appetite_observation",
        ["observed_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_appetite_observation_person_id"),
        "person_appetite_observation",
        ["person_id"],
        unique=False,
    )
    op.create_table(
        "person_assessment_embeddings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "embedding_vector",
            pgvector.sqlalchemy.VECTOR(dim=384).with_variant(sa.JSON(), "sqlite"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("person_assessment_id", sa.Integer(), nullable=False),
        sa.Column("model_name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.ForeignKeyConstraint(
            ["person_assessment_id"],
            ["person_assessment.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_person_assessment_embeddings_embedding_vector_hnsw",
        "person_assessment_embeddings",
        ["embedding_vector"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_ops={"embedding_vector": "vector_cosine_ops"},
    )
    op.create_index(
        op.f("ix_person_assessment_embeddings_person_assessment_id"),
        "person_assessment_embeddings",
        ["person_assessment_id"],
        unique=True,
    )
    op.create_table(
        "person_clinical_fact",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=False),
        sa.Column(
            "clinical_fact_type",
            postgresql.ENUM(
                "observation",
                "event",
                name="clinical_fact_type",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "observation_type",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=False,
        ),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("severity", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("description", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("observed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("extracted_fact_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["extracted_fact_id"],
            ["extracted_fact.id"],
        ),
        sa.ForeignKeyConstraint(
            ["person_id"],
            ["person.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_person_clinical_fact_clinical_fact_type"),
        "person_clinical_fact",
        ["clinical_fact_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_clinical_fact_created_at"),
        "person_clinical_fact",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_clinical_fact_extracted_fact_id"),
        "person_clinical_fact",
        ["extracted_fact_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_person_clinical_fact_observation_type"),
        "person_clinical_fact",
        ["observation_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_clinical_fact_observed_at"),
        "person_clinical_fact",
        ["observed_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_clinical_fact_person_id"),
        "person_clinical_fact",
        ["person_id"],
        unique=False,
    )
    op.create_table(
        "person_diagnosis",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=False),
        sa.Column("diagnosis", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("code", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("code_system", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(
                "ACTIVE",
                "INACTIVE",
                "HISTORICAL",
                "UNKNOWN",
                name="clinicalstatus",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("observed_at", sa.DateTime(), nullable=True),
        sa.Column("effective_at", sa.DateTime(), nullable=True),
        sa.Column("discontinued_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column(
            "state_key",
            sqlmodel.sql.sqltypes.AutoString(length=64),
            nullable=False,
        ),
        sa.Column("extracted_fact_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["extracted_fact_id"],
            ["extracted_fact.id"],
        ),
        sa.ForeignKeyConstraint(
            ["person_id"],
            ["person.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("person_id", "state_key"),
    )
    op.create_index(
        op.f("ix_person_diagnosis_code"),
        "person_diagnosis",
        ["code"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_diagnosis_created_at"),
        "person_diagnosis",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_diagnosis_diagnosis"),
        "person_diagnosis",
        ["diagnosis"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_diagnosis_discontinued_at"),
        "person_diagnosis",
        ["discontinued_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_diagnosis_effective_at"),
        "person_diagnosis",
        ["effective_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_diagnosis_extracted_fact_id"),
        "person_diagnosis",
        ["extracted_fact_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_person_diagnosis_observed_at"),
        "person_diagnosis",
        ["observed_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_diagnosis_person_id"),
        "person_diagnosis",
        ["person_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_diagnosis_state_key"),
        "person_diagnosis",
        ["state_key"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_diagnosis_status"),
        "person_diagnosis",
        ["status"],
        unique=False,
    )
    op.create_table(
        "person_dialysis",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=False),
        sa.Column(
            "dialysis_type",
            postgresql.ENUM(
                "HEMODIALYSIS",
                "PERITONEAL_DIALYSIS",
                "OTHER",
                "UNKNOWN",
                name="dialysistype",
                create_type=False,
            ),
            nullable=True,
        ),
        sa.Column("schedule", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(
                "ACTIVE",
                "INACTIVE",
                "HISTORICAL",
                "UNKNOWN",
                name="clinicalstatus",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("effective_at", sa.DateTime(), nullable=True),
        sa.Column("discontinued_at", sa.DateTime(), nullable=True),
        sa.Column("observed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column(
            "state_key",
            sqlmodel.sql.sqltypes.AutoString(length=64),
            nullable=False,
        ),
        sa.Column("extracted_fact_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["extracted_fact_id"],
            ["extracted_fact.id"],
        ),
        sa.ForeignKeyConstraint(
            ["person_id"],
            ["person.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("person_id", "state_key"),
    )
    op.create_index(
        op.f("ix_person_dialysis_created_at"),
        "person_dialysis",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_dialysis_dialysis_type"),
        "person_dialysis",
        ["dialysis_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_dialysis_discontinued_at"),
        "person_dialysis",
        ["discontinued_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_dialysis_effective_at"),
        "person_dialysis",
        ["effective_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_dialysis_extracted_fact_id"),
        "person_dialysis",
        ["extracted_fact_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_person_dialysis_observed_at"),
        "person_dialysis",
        ["observed_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_dialysis_person_id"),
        "person_dialysis",
        ["person_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_dialysis_state_key"),
        "person_dialysis",
        ["state_key"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_dialysis_status"),
        "person_dialysis",
        ["status"],
        unique=False,
    )
    op.create_table(
        "person_diet",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=False),
        sa.Column("diet_type", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("texture", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column(
            "liquid_consistency",
            postgresql.ENUM(
                "THIN",
                "SLIGHTLY_THICK",
                "MILDLY_THICK",
                "MODERATELY_THICK",
                "EXTREMELY_THICK",
                name="liquidconsistency",
                create_type=False,
            ),
            nullable=True,
        ),
        sa.Column("restrictions", sa.JSON(), nullable=False),
        sa.Column("instructions", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(
                "ACTIVE",
                "INACTIVE",
                "HISTORICAL",
                "UNKNOWN",
                name="clinicalstatus",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("effective_at", sa.DateTime(), nullable=True),
        sa.Column("discontinued_at", sa.DateTime(), nullable=True),
        sa.Column("observed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column(
            "state_key",
            sqlmodel.sql.sqltypes.AutoString(length=64),
            nullable=False,
        ),
        sa.Column("extracted_fact_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["extracted_fact_id"],
            ["extracted_fact.id"],
        ),
        sa.ForeignKeyConstraint(
            ["person_id"],
            ["person.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "person_id",
            "state_key",
            name="person_diet_person_id_state_key_key",
        ),
    )
    op.create_index(
        op.f("ix_person_diet_created_at"),
        "person_diet",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_diet_diet_type"),
        "person_diet",
        ["diet_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_diet_discontinued_at"),
        "person_diet",
        ["discontinued_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_diet_effective_at"),
        "person_diet",
        ["effective_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_diet_extracted_fact_id"),
        "person_diet",
        ["extracted_fact_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_person_diet_liquid_consistency"),
        "person_diet",
        ["liquid_consistency"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_diet_observed_at"),
        "person_diet",
        ["observed_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_diet_person_id"),
        "person_diet",
        ["person_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_diet_state_key"),
        "person_diet",
        ["state_key"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_diet_status"),
        "person_diet",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_diet_texture"),
        "person_diet",
        ["texture"],
        unique=False,
    )
    op.create_table(
        "person_edema",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=False),
        sa.Column("location", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("severity", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("observed_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("extracted_fact_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["extracted_fact_id"],
            ["extracted_fact.id"],
        ),
        sa.ForeignKeyConstraint(
            ["person_id"],
            ["person.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("person_id", "location", "observed_at"),
    )
    op.create_index(
        op.f("ix_person_edema_created_at"),
        "person_edema",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_edema_extracted_fact_id"),
        "person_edema",
        ["extracted_fact_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_edema_observed_at"),
        "person_edema",
        ["observed_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_edema_person_id"),
        "person_edema",
        ["person_id"],
        unique=False,
    )
    op.create_table(
        "person_enteral_feeding",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=False),
        sa.Column("formula", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("route", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column(
            "feeding_method",
            postgresql.ENUM(
                "CONTINUOUS",
                "CYCLIC",
                "BOLUS",
                "UNKNOWN",
                name="feedingmethod",
                create_type=False,
            ),
            nullable=True,
        ),
        sa.Column("rate_ml_hr", sa.Float(), nullable=True),
        sa.Column("hours_per_day", sa.Float(), nullable=True),
        sa.Column("bolus_volume_ml", sa.Float(), nullable=True),
        sa.Column("boluses_per_day", sa.Integer(), nullable=True),
        sa.Column("flush_ml", sa.Float(), nullable=True),
        sa.Column("flush_frequency_hours", sa.Float(), nullable=True),
        sa.Column(
            "flush_instructions",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=True,
        ),
        sa.Column(
            "feeding_schedule",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=True,
        ),
        sa.Column(
            "package_type",
            postgresql.ENUM(
                "READY_TO_HANG",
                "CARTON",
                "BOTTLE",
                "CAN",
                name="packagetype",
                create_type=False,
            ),
            nullable=True,
        ),
        sa.Column("package_volume_ml", sa.Float(), nullable=True),
        sa.Column("caloric_density_kcal_ml", sa.Float(), nullable=True),
        sa.Column("instructions", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(
                "ACTIVE",
                "INACTIVE",
                "HISTORICAL",
                "UNKNOWN",
                name="clinicalstatus",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("effective_at", sa.DateTime(), nullable=True),
        sa.Column("discontinued_at", sa.DateTime(), nullable=True),
        sa.Column("observed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column(
            "state_key",
            sqlmodel.sql.sqltypes.AutoString(length=64),
            nullable=False,
        ),
        sa.Column("extracted_fact_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["extracted_fact_id"],
            ["extracted_fact.id"],
        ),
        sa.ForeignKeyConstraint(
            ["person_id"],
            ["person.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("person_id", "state_key"),
    )
    op.create_index(
        op.f("ix_person_enteral_feeding_created_at"),
        "person_enteral_feeding",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_enteral_feeding_discontinued_at"),
        "person_enteral_feeding",
        ["discontinued_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_enteral_feeding_effective_at"),
        "person_enteral_feeding",
        ["effective_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_enteral_feeding_extracted_fact_id"),
        "person_enteral_feeding",
        ["extracted_fact_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_person_enteral_feeding_feeding_method"),
        "person_enteral_feeding",
        ["feeding_method"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_enteral_feeding_formula"),
        "person_enteral_feeding",
        ["formula"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_enteral_feeding_observed_at"),
        "person_enteral_feeding",
        ["observed_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_enteral_feeding_package_type"),
        "person_enteral_feeding",
        ["package_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_enteral_feeding_person_id"),
        "person_enteral_feeding",
        ["person_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_enteral_feeding_state_key"),
        "person_enteral_feeding",
        ["state_key"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_enteral_feeding_status"),
        "person_enteral_feeding",
        ["status"],
        unique=False,
    )
    op.create_table(
        "person_fluid_plan",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=False),
        sa.Column("target_ml_day", sa.Float(), nullable=True),
        sa.Column("restriction_ml_day", sa.Float(), nullable=True),
        sa.Column("instructions", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(
                "ACTIVE",
                "INACTIVE",
                "HISTORICAL",
                "UNKNOWN",
                name="clinicalstatus",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("effective_at", sa.DateTime(), nullable=True),
        sa.Column("discontinued_at", sa.DateTime(), nullable=True),
        sa.Column("observed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column(
            "state_key",
            sqlmodel.sql.sqltypes.AutoString(length=64),
            nullable=False,
        ),
        sa.Column("extracted_fact_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["extracted_fact_id"],
            ["extracted_fact.id"],
        ),
        sa.ForeignKeyConstraint(
            ["person_id"],
            ["person.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("person_id", "state_key"),
    )
    op.create_index(
        op.f("ix_person_fluid_plan_created_at"),
        "person_fluid_plan",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_fluid_plan_discontinued_at"),
        "person_fluid_plan",
        ["discontinued_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_fluid_plan_effective_at"),
        "person_fluid_plan",
        ["effective_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_fluid_plan_extracted_fact_id"),
        "person_fluid_plan",
        ["extracted_fact_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_person_fluid_plan_observed_at"),
        "person_fluid_plan",
        ["observed_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_fluid_plan_person_id"),
        "person_fluid_plan",
        ["person_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_fluid_plan_state_key"),
        "person_fluid_plan",
        ["state_key"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_fluid_plan_status"),
        "person_fluid_plan",
        ["status"],
        unique=False,
    )
    op.create_table(
        "person_food_preference",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=False),
        sa.Column(
            "preference_type",
            postgresql.ENUM(
                "FOOD",
                "BEVERAGE",
                "CUISINE",
                "MEAL_PATTERN",
                "DIETARY_PRACTICE",
                "OTHER",
                name="foodpreferencetype",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("item", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column(
            "preference",
            postgresql.ENUM(
                "LIKES",
                "DISLIKES",
                "PREFERS",
                "AVOIDS",
                "REQUIRES",
                name="foodpreferencevalue",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "reason",
            postgresql.ENUM(
                "PERSONAL",
                "CULTURAL",
                "RELIGIOUS",
                "ETHICAL",
                "OTHER",
                "UNKNOWN",
                name="foodpreferencereason",
                create_type=False,
            ),
            nullable=True,
        ),
        sa.Column("notes", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(
                "ACTIVE",
                "INACTIVE",
                "HISTORICAL",
                "UNKNOWN",
                name="clinicalstatus",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("observed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column(
            "state_key",
            sqlmodel.sql.sqltypes.AutoString(length=64),
            nullable=False,
        ),
        sa.Column("extracted_fact_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["extracted_fact_id"],
            ["extracted_fact.id"],
        ),
        sa.ForeignKeyConstraint(
            ["person_id"],
            ["person.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("person_id", "state_key"),
    )
    op.create_index(
        op.f("ix_person_food_preference_created_at"),
        "person_food_preference",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_food_preference_extracted_fact_id"),
        "person_food_preference",
        ["extracted_fact_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_person_food_preference_item"),
        "person_food_preference",
        ["item"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_food_preference_observed_at"),
        "person_food_preference",
        ["observed_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_food_preference_person_id"),
        "person_food_preference",
        ["person_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_food_preference_preference"),
        "person_food_preference",
        ["preference"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_food_preference_preference_type"),
        "person_food_preference",
        ["preference_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_food_preference_reason"),
        "person_food_preference",
        ["reason"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_food_preference_state_key"),
        "person_food_preference",
        ["state_key"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_food_preference_status"),
        "person_food_preference",
        ["status"],
        unique=False,
    )
    op.create_table(
        "person_gi_observation",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=False),
        sa.Column(
            "symptom",
            postgresql.ENUM(
                "NAUSEA",
                "VOMITING",
                "DIARRHEA",
                "CONSTIPATION",
                "ABDOMINAL_PAIN",
                "EARLY_SATIETY",
                "BLOATING",
                "REFLUX",
                "OTHER",
                name="gisymptom",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("severity", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("notes", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("observed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column(
            "observation_key",
            sqlmodel.sql.sqltypes.AutoString(length=64),
            nullable=False,
        ),
        sa.Column("extracted_fact_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["extracted_fact_id"],
            ["extracted_fact.id"],
        ),
        sa.ForeignKeyConstraint(
            ["person_id"],
            ["person.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_person_gi_observation_created_at"),
        "person_gi_observation",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_gi_observation_extracted_fact_id"),
        "person_gi_observation",
        ["extracted_fact_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_person_gi_observation_observation_key"),
        "person_gi_observation",
        ["observation_key"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_gi_observation_observed_at"),
        "person_gi_observation",
        ["observed_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_gi_observation_person_id"),
        "person_gi_observation",
        ["person_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_gi_observation_symptom"),
        "person_gi_observation",
        ["symptom"],
        unique=False,
    )
    op.create_table(
        "person_lab",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("result", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("unit", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("flag", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("reference_range", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("observed_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("extracted_fact_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["extracted_fact_id"],
            ["extracted_fact.id"],
        ),
        sa.ForeignKeyConstraint(
            ["person_id"],
            ["person.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("person_id", "name", "observed_at"),
    )
    op.create_index(
        op.f("ix_person_lab_created_at"),
        "person_lab",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_lab_extracted_fact_id"),
        "person_lab",
        ["extracted_fact_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_lab_observed_at"),
        "person_lab",
        ["observed_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_lab_person_id"),
        "person_lab",
        ["person_id"],
        unique=False,
    )
    op.create_table(
        "person_meal_intake",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=False),
        sa.Column("min_percent", sa.Float(), nullable=True),
        sa.Column("max_percent", sa.Float(), nullable=True),
        sa.Column("observed_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("extracted_fact_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["extracted_fact_id"],
            ["extracted_fact.id"],
        ),
        sa.ForeignKeyConstraint(
            ["person_id"],
            ["person.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_person_meal_intake_created_at"),
        "person_meal_intake",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_meal_intake_extracted_fact_id"),
        "person_meal_intake",
        ["extracted_fact_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_meal_intake_observed_at"),
        "person_meal_intake",
        ["observed_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_meal_intake_person_id"),
        "person_meal_intake",
        ["person_id"],
        unique=False,
    )
    op.create_table(
        "person_medication",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("dose", sa.Float(), nullable=True),
        sa.Column("dose_text", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("dose_unit", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("route", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("frequency", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("indication", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("instructions", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(
                "ACTIVE",
                "INACTIVE",
                "HISTORICAL",
                "UNKNOWN",
                name="clinicalstatus",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("effective_at", sa.DateTime(), nullable=True),
        sa.Column("discontinued_at", sa.DateTime(), nullable=True),
        sa.Column("observed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column(
            "state_key",
            sqlmodel.sql.sqltypes.AutoString(length=64),
            nullable=False,
        ),
        sa.Column("extracted_fact_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["extracted_fact_id"],
            ["extracted_fact.id"],
        ),
        sa.ForeignKeyConstraint(
            ["person_id"],
            ["person.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("person_id", "state_key"),
    )
    op.create_index(
        op.f("ix_person_medication_created_at"),
        "person_medication",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_medication_discontinued_at"),
        "person_medication",
        ["discontinued_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_medication_effective_at"),
        "person_medication",
        ["effective_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_medication_extracted_fact_id"),
        "person_medication",
        ["extracted_fact_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_person_medication_name"),
        "person_medication",
        ["name"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_medication_observed_at"),
        "person_medication",
        ["observed_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_medication_person_id"),
        "person_medication",
        ["person_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_medication_state_key"),
        "person_medication",
        ["state_key"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_medication_status"),
        "person_medication",
        ["status"],
        unique=False,
    )
    op.create_table(
        "person_misc_order",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=False),
        sa.Column("order_type", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("description", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(
                "ACTIVE",
                "INACTIVE",
                "HISTORICAL",
                "UNKNOWN",
                name="clinicalstatus",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("effective_at", sa.DateTime(), nullable=True),
        sa.Column("discontinued_at", sa.DateTime(), nullable=True),
        sa.Column("observed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column(
            "state_key",
            sqlmodel.sql.sqltypes.AutoString(length=64),
            nullable=False,
        ),
        sa.Column("extracted_fact_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["extracted_fact_id"],
            ["extracted_fact.id"],
        ),
        sa.ForeignKeyConstraint(
            ["person_id"],
            ["person.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("person_id", "state_key"),
    )
    op.create_index(
        op.f("ix_person_misc_order_created_at"),
        "person_misc_order",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_misc_order_discontinued_at"),
        "person_misc_order",
        ["discontinued_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_misc_order_effective_at"),
        "person_misc_order",
        ["effective_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_misc_order_extracted_fact_id"),
        "person_misc_order",
        ["extracted_fact_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_person_misc_order_observed_at"),
        "person_misc_order",
        ["observed_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_misc_order_order_type"),
        "person_misc_order",
        ["order_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_misc_order_person_id"),
        "person_misc_order",
        ["person_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_misc_order_state_key"),
        "person_misc_order",
        ["state_key"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_misc_order_status"),
        "person_misc_order",
        ["status"],
        unique=False,
    )
    op.create_table(
        "person_nutrition_goal",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=False),
        sa.Column(
            "goal_type",
            postgresql.ENUM(
                "WEIGHT_GAIN",
                "WEIGHT_MAINTENANCE",
                "WEIGHT_LOSS",
                "INCREASE_PROTEIN",
                "INCREASE_CALORIES",
                "INCREASE_FLUID",
                "FLUID_RESTRICTION",
                "IMPROVE_MEAL_INTAKE",
                "INCREASE_FIBER",
                "REDUCE_SODIUM",
                "OTHER",
                name="nutritiongoaltype",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("target_value", sa.Float(), nullable=True),
        sa.Column("target_unit", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("target_date", sa.Date(), nullable=True),
        sa.Column("notes", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(
                "ACTIVE",
                "INACTIVE",
                "HISTORICAL",
                "UNKNOWN",
                name="clinicalstatus",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("effective_at", sa.DateTime(), nullable=True),
        sa.Column("discontinued_at", sa.DateTime(), nullable=True),
        sa.Column("observed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column(
            "state_key",
            sqlmodel.sql.sqltypes.AutoString(length=64),
            nullable=False,
        ),
        sa.Column("extracted_fact_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["extracted_fact_id"],
            ["extracted_fact.id"],
        ),
        sa.ForeignKeyConstraint(
            ["person_id"],
            ["person.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("person_id", "state_key"),
    )
    op.create_index(
        op.f("ix_person_nutrition_goal_created_at"),
        "person_nutrition_goal",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_nutrition_goal_discontinued_at"),
        "person_nutrition_goal",
        ["discontinued_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_nutrition_goal_effective_at"),
        "person_nutrition_goal",
        ["effective_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_nutrition_goal_extracted_fact_id"),
        "person_nutrition_goal",
        ["extracted_fact_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_person_nutrition_goal_goal_type"),
        "person_nutrition_goal",
        ["goal_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_nutrition_goal_observed_at"),
        "person_nutrition_goal",
        ["observed_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_nutrition_goal_person_id"),
        "person_nutrition_goal",
        ["person_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_nutrition_goal_state_key"),
        "person_nutrition_goal",
        ["state_key"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_nutrition_goal_status"),
        "person_nutrition_goal",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_nutrition_goal_target_date"),
        "person_nutrition_goal",
        ["target_date"],
        unique=False,
    )
    op.create_table(
        "person_oral_feeding_status",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=False),
        sa.Column(
            "dentition_status",
            postgresql.ENUM(
                "NATURAL",
                "PARTIAL_DENTITION",
                "EDENTULOUS",
                "DENTURES",
                "UNKNOWN",
                name="dentitionstatus",
                create_type=False,
            ),
            nullable=True,
        ),
        sa.Column(
            "upper_denture",
            postgresql.ENUM(
                "PRESENT",
                "ABSENT",
                "PARTIAL",
                "NOT_WORN",
                "UNAVAILABLE",
                "UNKNOWN",
                name="denturestatus",
                create_type=False,
            ),
            nullable=True,
        ),
        sa.Column(
            "lower_denture",
            postgresql.ENUM(
                "PRESENT",
                "ABSENT",
                "PARTIAL",
                "NOT_WORN",
                "UNAVAILABLE",
                "UNKNOWN",
                name="denturestatus",
                create_type=False,
            ),
            nullable=True,
        ),
        sa.Column("chewing_difficulty", sa.Boolean(), nullable=True),
        sa.Column("swallowing_difficulty", sa.Boolean(), nullable=True),
        sa.Column("dysphagia", sa.Boolean(), nullable=True),
        sa.Column("aspiration_risk", sa.Boolean(), nullable=True),
        sa.Column("slp_following", sa.Boolean(), nullable=True),
        sa.Column("notes", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(
                "ACTIVE",
                "INACTIVE",
                "HISTORICAL",
                "UNKNOWN",
                name="clinicalstatus",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("observed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column(
            "state_key",
            sqlmodel.sql.sqltypes.AutoString(length=64),
            nullable=False,
        ),
        sa.Column("extracted_fact_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["extracted_fact_id"],
            ["extracted_fact.id"],
        ),
        sa.ForeignKeyConstraint(
            ["person_id"],
            ["person.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("person_id", "state_key"),
    )
    op.create_index(
        op.f("ix_person_oral_feeding_status_created_at"),
        "person_oral_feeding_status",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_oral_feeding_status_dentition_status"),
        "person_oral_feeding_status",
        ["dentition_status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_oral_feeding_status_extracted_fact_id"),
        "person_oral_feeding_status",
        ["extracted_fact_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_person_oral_feeding_status_observed_at"),
        "person_oral_feeding_status",
        ["observed_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_oral_feeding_status_person_id"),
        "person_oral_feeding_status",
        ["person_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_oral_feeding_status_state_key"),
        "person_oral_feeding_status",
        ["state_key"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_oral_feeding_status_status"),
        "person_oral_feeding_status",
        ["status"],
        unique=False,
    )
    op.create_table(
        "person_parenteral_nutrition",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=False),
        sa.Column(
            "access_route",
            postgresql.ENUM(
                "CENTRAL",
                "PERIPHERAL",
                "UNKNOWN",
                name="parenteralaccessroute",
                create_type=False,
            ),
            nullable=True,
        ),
        sa.Column(
            "access_description",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=True,
        ),
        sa.Column(
            "formula_type",
            postgresql.ENUM(
                "STANDARD",
                "CONCENTRATED",
                "CUSTOM",
                "UNKNOWN",
                name="parenteralformulatype",
                create_type=False,
            ),
            nullable=True,
        ),
        sa.Column("total_volume_ml", sa.Float(), nullable=True),
        sa.Column("rate_ml_hr", sa.Float(), nullable=True),
        sa.Column("daily_start_time", sa.Time(), nullable=True),
        sa.Column("hours_per_day", sa.Float(), nullable=True),
        sa.Column("dextrose_g_per_l", sa.Float(), nullable=True),
        sa.Column("amino_acid_g_per_l", sa.Float(), nullable=True),
        sa.Column("documented_protein_g", sa.Float(), nullable=True),
        sa.Column("documented_calories_kcal", sa.Float(), nullable=True),
        sa.Column(
            "lipid_delivery",
            postgresql.ENUM(
                "INCLUDED",
                "PIGGYBACK",
                "NONE",
                "UNKNOWN",
                name="lipiddeliverytype",
                create_type=False,
            ),
            nullable=True,
        ),
        sa.Column("lipid_concentration_percent", sa.Float(), nullable=True),
        sa.Column("lipid_total_volume_ml", sa.Float(), nullable=True),
        sa.Column("lipid_run_time_hours", sa.Float(), nullable=True),
        sa.Column("lipid_rate_ml_hr", sa.Float(), nullable=True),
        sa.Column("instructions", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(
                "ACTIVE",
                "INACTIVE",
                "HISTORICAL",
                "UNKNOWN",
                name="parenteralnutritionstatus",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("effective_at", sa.DateTime(), nullable=True),
        sa.Column("discontinued_at", sa.DateTime(), nullable=True),
        sa.Column("observed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column(
            "state_key",
            sqlmodel.sql.sqltypes.AutoString(length=64),
            nullable=False,
        ),
        sa.Column("extracted_fact_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["extracted_fact_id"],
            ["extracted_fact.id"],
        ),
        sa.ForeignKeyConstraint(
            ["person_id"],
            ["person.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("person_id", "state_key"),
    )
    op.create_index(
        op.f("ix_person_parenteral_nutrition_access_route"),
        "person_parenteral_nutrition",
        ["access_route"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_parenteral_nutrition_created_at"),
        "person_parenteral_nutrition",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_parenteral_nutrition_discontinued_at"),
        "person_parenteral_nutrition",
        ["discontinued_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_parenteral_nutrition_effective_at"),
        "person_parenteral_nutrition",
        ["effective_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_parenteral_nutrition_extracted_fact_id"),
        "person_parenteral_nutrition",
        ["extracted_fact_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_person_parenteral_nutrition_formula_type"),
        "person_parenteral_nutrition",
        ["formula_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_parenteral_nutrition_lipid_delivery"),
        "person_parenteral_nutrition",
        ["lipid_delivery"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_parenteral_nutrition_observed_at"),
        "person_parenteral_nutrition",
        ["observed_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_parenteral_nutrition_person_id"),
        "person_parenteral_nutrition",
        ["person_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_parenteral_nutrition_state_key"),
        "person_parenteral_nutrition",
        ["state_key"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_parenteral_nutrition_status"),
        "person_parenteral_nutrition",
        ["status"],
        unique=False,
    )
    op.create_table(
        "person_supplement",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=False),
        sa.Column("product_name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("amount", sa.Float(), nullable=True),
        sa.Column("unit", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("frequency", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("route", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("instructions", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(
                "ACTIVE",
                "INACTIVE",
                "HISTORICAL",
                "UNKNOWN",
                name="clinicalstatus",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("effective_at", sa.DateTime(), nullable=True),
        sa.Column("discontinued_at", sa.DateTime(), nullable=True),
        sa.Column("observed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column(
            "state_key",
            sqlmodel.sql.sqltypes.AutoString(length=64),
            nullable=False,
        ),
        sa.Column("extracted_fact_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["extracted_fact_id"],
            ["extracted_fact.id"],
        ),
        sa.ForeignKeyConstraint(
            ["person_id"],
            ["person.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("person_id", "state_key"),
    )
    op.create_index(
        op.f("ix_person_supplement_created_at"),
        "person_supplement",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_supplement_discontinued_at"),
        "person_supplement",
        ["discontinued_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_supplement_effective_at"),
        "person_supplement",
        ["effective_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_supplement_extracted_fact_id"),
        "person_supplement",
        ["extracted_fact_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_person_supplement_observed_at"),
        "person_supplement",
        ["observed_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_supplement_person_id"),
        "person_supplement",
        ["person_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_supplement_product_name"),
        "person_supplement",
        ["product_name"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_supplement_state_key"),
        "person_supplement",
        ["state_key"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_supplement_status"),
        "person_supplement",
        ["status"],
        unique=False,
    )
    op.create_table(
        "person_weight",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=False),
        sa.Column("measured_at", sa.DateTime(), nullable=False),
        sa.Column("weight_lb", sa.Float(), nullable=False),
        sa.Column("description", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column(
            "weight_context",
            postgresql.ENUM(
                "ROUTINE",
                "PRE_DIALYSIS",
                "POST_DIALYSIS",
                "DRY_WEIGHT",
                "TARGET_WEIGHT",
                "UNKNOWN",
                name="weightcontext",
                create_type=False,
            ),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("extracted_fact_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["extracted_fact_id"],
            ["extracted_fact.id"],
        ),
        sa.ForeignKeyConstraint(
            ["person_id"],
            ["person.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("person_id", "measured_at"),
    )
    op.create_index(
        op.f("ix_person_weight_created_at"),
        "person_weight",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_weight_extracted_fact_id"),
        "person_weight",
        ["extracted_fact_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_weight_measured_at"),
        "person_weight",
        ["measured_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_weight_person_id"),
        "person_weight",
        ["person_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_weight_weight_context"),
        "person_weight",
        ["weight_context"],
        unique=False,
    )
    op.create_table(
        "person_wound",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=False),
        sa.Column("wound_number", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("type", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("location", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("weeks_in_treatment", sa.Integer(), nullable=True),
        sa.Column("progress", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("stage", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("size", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("assessment_note", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column(
            "physician_orders",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=True,
        ),
        sa.Column(
            "physician_orders_notes",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=True,
        ),
        sa.Column("observed_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("extracted_fact_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["extracted_fact_id"],
            ["extracted_fact.id"],
        ),
        sa.ForeignKeyConstraint(
            ["person_id"],
            ["person.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("person_id", "wound_number", "observed_at"),
    )
    op.create_index(
        op.f("ix_person_wound_created_at"),
        "person_wound",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_wound_extracted_fact_id"),
        "person_wound",
        ["extracted_fact_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_wound_observed_at"),
        "person_wound",
        ["observed_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_wound_person_id"),
        "person_wound",
        ["person_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_wound_wound_number"),
        "person_wound",
        ["wound_number"],
        unique=False,
    )


def downgrade() -> None:
    """Drop all application tables while retaining the shared vector extension."""
    op.drop_table("person_wound")
    op.drop_table("person_weight")
    op.drop_table("person_supplement")
    op.drop_table("person_parenteral_nutrition")
    op.drop_table("person_oral_feeding_status")
    op.drop_table("person_nutrition_goal")
    op.drop_table("person_misc_order")
    op.drop_table("person_medication")
    op.drop_table("person_meal_intake")
    op.drop_table("person_lab")
    op.drop_table("person_gi_observation")
    op.drop_table("person_food_preference")
    op.drop_table("person_fluid_plan")
    op.drop_table("person_enteral_feeding")
    op.drop_table("person_edema")
    op.drop_table("person_diet")
    op.drop_table("person_dialysis")
    op.drop_table("person_diagnosis")
    op.drop_table("person_clinical_fact")
    op.drop_table("person_assessment_embeddings")
    op.drop_table("person_appetite_observation")
    op.drop_table("person_allergy")
    op.drop_table("person_assessment")
    op.drop_table("extracted_fact")
    op.drop_table("person_progress_note")
    op.drop_table("knowledge_chunks_embeddings")
    op.drop_table("food_nutrient")
    op.drop_table("document_source")
    op.drop_table("user_hash")
    op.drop_table("person")
    op.drop_table("knowledge_chunks")
    op.drop_table("food")
    op.drop_table("document")
    op.drop_table("api_key_permission")
    op.drop_table("user")
    op.drop_table("permission")
    op.drop_table("nutrient")
    op.drop_table("knowledge")
    op.drop_table("food_sync_state")
    op.drop_table("food_category")
    op.drop_table("facility")
    op.drop_table("api_key")
    op.execute("DROP TYPE IF EXISTS appetitelevel")
    op.execute("DROP TYPE IF EXISTS clinical_fact_type")
    op.execute("DROP TYPE IF EXISTS clinicalstatus")
    op.execute("DROP TYPE IF EXISTS dentitionstatus")
    op.execute("DROP TYPE IF EXISTS denturestatus")
    op.execute("DROP TYPE IF EXISTS dialysistype")
    op.execute("DROP TYPE IF EXISTS documentsourcetype")
    op.execute("DROP TYPE IF EXISTS extraction_status")
    op.execute("DROP TYPE IF EXISTS extractionmethod")
    op.execute("DROP TYPE IF EXISTS feedingmethod")
    op.execute("DROP TYPE IF EXISTS foodcategorysource")
    op.execute("DROP TYPE IF EXISTS foodpreferencereason")
    op.execute("DROP TYPE IF EXISTS foodpreferencetype")
    op.execute("DROP TYPE IF EXISTS foodpreferencevalue")
    op.execute("DROP TYPE IF EXISTS foodsourcetype")
    op.execute("DROP TYPE IF EXISTS foodtype")
    op.execute("DROP TYPE IF EXISTS gisymptom")
    op.execute("DROP TYPE IF EXISTS importmethod")
    op.execute("DROP TYPE IF EXISTS lipiddeliverytype")
    op.execute("DROP TYPE IF EXISTS liquidconsistency")
    op.execute("DROP TYPE IF EXISTS nutrientclassification")
    op.execute("DROP TYPE IF EXISTS nutritiongoaltype")
    op.execute("DROP TYPE IF EXISTS packagetype")
    op.execute("DROP TYPE IF EXISTS parenteralaccessroute")
    op.execute("DROP TYPE IF EXISTS parenteralformulatype")
    op.execute("DROP TYPE IF EXISTS parenteralnutritionstatus")
    op.execute("DROP TYPE IF EXISTS sourceauthority")
    op.execute("DROP TYPE IF EXISTS status_type")
    op.execute("DROP TYPE IF EXISTS weightcontext")
