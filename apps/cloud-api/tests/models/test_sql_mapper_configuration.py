from __future__ import annotations

from sqlalchemy import Integer
from sqlalchemy.orm import configure_mappers
from sqlmodel import SQLModel

import api.models.sql  # noqa: F401


def test_sqlalchemy_mappers_configure() -> None:
    """Ensure every declared relationship resolves its target and reverse side."""
    configure_mappers()


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


def test_ncp_and_api_key_tables_are_registered() -> None:
    assert "nutrition_care_process" in SQLModel.metadata.tables
    assert "api_key" in SQLModel.metadata.tables
    assert "person" not in SQLModel.metadata.tables
