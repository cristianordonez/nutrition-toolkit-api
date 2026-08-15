# noqa: I002
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlmodel import Field, Relationship, SQLModel


class Ticket(SQLModel, table=True):
    """Ticket model."""

    __tablename__ = "ticket"

    ticket_id: UUID = Field(default_factory=uuid4, primary_key=True)
    title: str
    status: str = Field(default="open")
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    messages: list["TicketMessage"] = Relationship(
        back_populates="ticket",
        sa_relationship_kwargs={"lazy": "selectin"},
    )


class TicketMessage(SQLModel, table=True):
    """Message attached to a ticket."""

    __tablename__ = "ticket_message"

    message_id: UUID = Field(default_factory=uuid4, primary_key=True)
    ticket_id: UUID = Field(foreign_key="ticket.ticket_id")
    message_text: str
    author: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    ticket: "Ticket" = Relationship(back_populates="messages")


class TicketMessagePublic(SQLModel):
    message_id: UUID
    ticket_id: UUID
    message_text: str
    author: str
    created_at: datetime


class TicketPublic(SQLModel):
    """Model for API response."""

    ticket_id: UUID
    title: str
    status: str
    created_by: str
    created_at: datetime
    messages: list[TicketMessagePublic] = []
