from __future__ import annotations

from sqlalchemy import Integer
from sqlalchemy.orm import configure_mappers
from sqlmodel import SQLModel

import ntk.models.sql  # noqa: F401
from ntk.models.sql.resident import Resident


def test_sqlalchemy_mappers_configure() -> None:
    """Ensure every declared relationship resolves its target and reverse side."""
    configure_mappers()


def test_resident_delete_never_nulls_assessment_foreign_keys() -> None:
    """Leave required assessment ownership enforcement to the database."""
    assert Resident.assessments.property.passive_deletes == "all"  # ty: ignore[unresolved-attribute]


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


def test_resident_dialysis_uses_clinical_fact_table() -> None:
    assert "resident_dialysis" not in SQLModel.metadata.tables
    assert "resident_clinical_fact" in SQLModel.metadata.tables
