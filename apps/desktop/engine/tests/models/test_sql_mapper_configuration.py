from __future__ import annotations

from sqlalchemy import Integer
from sqlalchemy.orm import configure_mappers
from sqlmodel import SQLModel

import engine.models.sql  # noqa: F401
from engine.models.sql.person import Person


def test_sqlalchemy_mappers_configure() -> None:
    """Ensure every declared relationship resolves its target and reverse side."""
    configure_mappers()


def test_person_forward_relationships_are_collections() -> None:
    """Keep one-to-many relationships declared before their models as lists."""
    assert Person.clinical_sources.property.uselist is True  # ty: ignore[unresolved-attribute]
    assert Person.clinical_facts.property.uselist is True  # ty: ignore[unresolved-attribute]
    assert Person.ncp_notes.property.uselist is True  # ty: ignore[unresolved-attribute]


def test_all_table_primary_keys_are_integers() -> None:
    """Ensure every SQL table uses integer primary and foreign identities."""
    for table in SQLModel.metadata.sorted_tables:
        assert table.primary_key.columns
        assert all(
            isinstance(column.type, Integer) for column in table.primary_key.columns
        ), table.name
        assert all(
            isinstance(foreign_key.parent.type, Integer)
            for foreign_key in table.foreign_keys
        ), table.name


def test_clinical_domains_share_one_fact_table() -> None:
    assert "clinical_fact" in SQLModel.metadata.tables
    for removed in (
        "person_dialysis",
        "person_clinical_fact",
        "person_order",
        "person_weight",
        "person_lab",
    ):
        assert removed not in SQLModel.metadata.tables
