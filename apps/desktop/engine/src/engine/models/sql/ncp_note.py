"""Persisted Nutrition Care Process notes and examples."""

from __future__ import annotations

import typing
from datetime import datetime  # noqa: TC003

from sqlalchemy import CheckConstraint, Column, Enum, Index
from sqlmodel import Field, Relationship, SQLModel

from engine.models.clinical_facts import utc_now
from engine.models.ncp_note import NCPNoteStatus, NCPNoteType

if typing.TYPE_CHECKING:
    from .facility import Facility
    from .person import Person


class NCPNote(SQLModel, table=True):
    """An NCP note, including global style examples shipped with the app."""

    __tablename__ = "ncp_note"
    __table_args__ = (
        CheckConstraint(
            "status != 'finalized' OR finalized_at IS NOT NULL",
            name="ck_ncp_note_finalized_at",
        ),
        Index(
            "ix_ncp_note_person_status_finalized",
            "person_id",
            "status",
            "finalized_at",
        ),
        Index(
            "ix_ncp_note_facility_status_type",
            "facility_id",
            "status",
            "note_type",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    person_id: int | None = Field(
        default=None,
        foreign_key="person.id",
        index=True,
        ondelete="CASCADE",
    )
    facility_id: int | None = Field(
        default=None,
        foreign_key="facility.id",
        index=True,
        ondelete="CASCADE",
    )
    note_type: NCPNoteType = Field(
        sa_column=Column(
            Enum(
                NCPNoteType,
                name="ncp_note_type",
                values_callable=lambda enum_type: [item.value for item in enum_type],
            ),
            nullable=False,
            index=True,
        ),
    )
    content: str
    status: NCPNoteStatus = Field(
        default=NCPNoteStatus.DRAFT,
        sa_column=Column(
            Enum(
                NCPNoteStatus,
                name="ncp_note_status",
                values_callable=lambda enum_type: [item.value for item in enum_type],
            ),
            nullable=False,
            default=NCPNoteStatus.DRAFT.value,
            index=True,
        ),
    )
    created_at: datetime = Field(default_factory=utc_now, index=True)
    updated_at: datetime = Field(default_factory=utc_now)
    finalized_at: datetime | None = Field(default=None, index=True)

    person: Person = Relationship(back_populates="ncp_notes")
    facility: Facility = Relationship(back_populates="ncp_notes")


__all__ = ["NCPNote", "NCPNoteStatus", "NCPNoteType"]
