from __future__ import annotations

from sqlalchemy import Integer
from sqlalchemy.orm import configure_mappers
from sqlmodel import SQLModel

import ntk.models.sql  # noqa: F401
from ntk.models.sql.person import Person


def test_sqlalchemy_mappers_configure() -> None:
    """Ensure every declared relationship resolves its target and reverse side."""
    configure_mappers()


def test_person_delete_never_nulls_assessment_foreign_keys() -> None:
    """Leave required assessment ownership enforcement to the database."""
    assert Person.assessments.property.passive_deletes == "all"  # ty: ignore[unresolved-attribute]


def test_person_forward_relationships_are_collections() -> None:
    """Keep one-to-many relationships declared before their models as lists."""
    assert Person.progress_notes.property.uselist is True  # ty: ignore[unresolved-attribute]
    assert Person.assessments.property.uselist is True  # ty: ignore[unresolved-attribute]


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


def test_person_dialysis_has_a_dedicated_domain_table() -> None:
    assert "person_dialysis" in SQLModel.metadata.tables
    assert "person_clinical_fact" in SQLModel.metadata.tables
    assert "person_order" not in SQLModel.metadata.tables
