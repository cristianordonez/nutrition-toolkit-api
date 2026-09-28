"""drop food and knowledge tables

The server no longer serves food data or the manual knowledge base; the desktop
engine keeps its own knowledge base on-device. Their models were removed from
``server.models.sql``, so their tables and the native enum types only they
used are dropped here. Existing rows are deleted with them.

Revision ID: 20260927_0000
Revises: 20260915_0000
Create Date: 2026-09-27 00:00:00
"""

# The downgrade restores the initial migration's generated table definitions
# unchanged (long lines, many statements).
# ruff: noqa: E501

from __future__ import annotations

import typing

import pgvector.sqlalchemy
import sqlalchemy as sa
import sqlmodel
from alembic import op

if typing.TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "20260927_0000"
down_revision: str | Sequence[str] | None = "20260915_0000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Native Postgres enum types used only by the dropped food tables. The
#: knowledge enum is a CHECK constraint (``native_enum=False``) and goes with
#: its table.
_FOOD_ENUM_TYPES = (
    "foodtype",
    "foodsourcetype",
    "importmethod",
    "liquidconsistency",
    "packagetype",
    "foodcategorysource",
    "nutrientclassification",
)


def upgrade() -> None:
    """Drop the food and knowledge tables, children before parents."""
    op.drop_index(
        op.f("ix_knowledge_chunks_embeddings_knowledge_chunk_id"),
        table_name="knowledge_chunks_embeddings",
    )
    op.drop_index(
        "ix_knowledge_chunks_embeddings_embedding_vector_hnsw",
        table_name="knowledge_chunks_embeddings",
        postgresql_using="hnsw",
        postgresql_ops={"embedding_vector": "vector_cosine_ops"},
    )
    op.drop_table("knowledge_chunks_embeddings")
    op.drop_index(
        op.f("ix_knowledge_chunks_knowledge_id"),
        table_name="knowledge_chunks",
    )
    op.drop_table("knowledge_chunks")
    op.drop_index(op.f("ix_knowledge_knowledge_type"), table_name="knowledge")
    op.drop_index(op.f("ix_knowledge_file_hash"), table_name="knowledge")
    op.drop_table("knowledge")

    op.drop_table("food_nutrient")
    op.drop_table("food")
    op.drop_table("nutrient")
    op.drop_index(op.f("ix_food_sync_state_source"), table_name="food_sync_state")
    op.drop_table("food_sync_state")
    op.drop_table("food_category")
    for enum_type in _FOOD_ENUM_TYPES:
        op.execute(f"DROP TYPE IF EXISTS {enum_type}")


def downgrade() -> None:
    """Recreate the tables empty, as the initial migration defined them."""
    op.create_table(
        "food_category",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column(
            "source",
            sa.Enum("USDA", "FATSECRET", "INTERNAL", name="foodcategorysource"),
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
            sa.Enum(
                "USDA_BRANDED",
                "USDA_FNDDS",
                "USDA_FOUNDATION",
                "USDA_SR_LEGACY",
                "FATSECRET",
                "MANUFACTURER",
                "INTERNAL",
                name="foodsourcetype",
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
            sa.Enum(
                "MACRONUTRIENT",
                "VITAMIN",
                "MINERAL",
                name="nutrientclassification",
            ),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "food",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column(
            "food_type",
            sa.Enum("FOOD", "ORAL_SUPPLEMENT", "ENTERAL_FORMULA", name="foodtype"),
            nullable=False,
        ),
        sa.Column(
            "source_type",
            sa.Enum(
                "USDA_BRANDED",
                "USDA_FNDDS",
                "USDA_FOUNDATION",
                "USDA_SR_LEGACY",
                "FATSECRET",
                "MANUFACTURER",
                "INTERNAL",
                name="foodsourcetype",
            ),
            nullable=False,
        ),
        sa.Column(
            "import_method",
            sa.Enum("API", "MANUAL", name="importmethod"),
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
            sa.Enum(
                "THIN",
                "SLIGHTLY_THICK",
                "MILDLY_THICK",
                "MODERATELY_THICK",
                "EXTREMELY_THICK",
                name="liquidconsistency",
            ),
            nullable=True,
        ),
        sa.Column(
            "package_type",
            sa.Enum("READY_TO_HANG", "CARTON", "BOTTLE", "CAN", name="packagetype"),
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
