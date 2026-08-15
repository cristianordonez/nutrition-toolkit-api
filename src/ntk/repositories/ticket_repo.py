from __future__ import annotations

import logging
import typing

from sqlmodel import Session, select

from ntk.models import Ticket, TicketMessage

if typing.TYPE_CHECKING:
    from collections.abc import Sequence
    from uuid import UUID

logger = logging.getLogger(__name__)


class TicketRepo:
    def __init__(self, session: Session) -> None:
        """Handle tickets and their messages.

        :param session: Database session
        """
        self.session = session

    def list_all(self) -> Sequence[Ticket]:
        """Return all tickets ordered by creation time."""
        statement = select(Ticket).order_by(Ticket.created_at)
        return self.session.exec(statement).all()

    def create(self, ticket: Ticket) -> Ticket:
        """Create a new ticket in the database.

        :param ticket: Ticket model
        :return: created ticket
        """
        self.session.add(ticket)
        self.session.commit()
        self.session.refresh(ticket)
        return ticket

    def add_message(
        self,
        ticket_id: UUID,
        message_text: str,
        author: str,
    ) -> TicketMessage:
        """Add a message to an existing ticket.

        :param ticket_id: UUID of the ticket
        :param message_text: message contents
        :param author: author of the message
        :return: created TicketMessage
        :raises ValueError: if ticket does not exist
        """
        ticket = self.session.exec(
            select(Ticket).where(Ticket.ticket_id == ticket_id),
        ).first()
        if ticket is None:
            msg = "Ticket not found"
            raise ValueError(msg)
        message = TicketMessage(
            ticket_id=ticket_id,
            message_text=message_text,
            author=author,
        )
        self.session.add(message)
        self.session.commit()
        self.session.refresh(message)
        self.session.refresh(ticket)
        return message

    def get_by_id(self, ticket_id: UUID) -> Ticket | None:
        """Retrieve a ticket by its id."""
        statement = select(Ticket).where(Ticket.ticket_id == ticket_id)
        return self.session.exec(statement).first()

    def update_status(self, ticket_id: UUID, status: str) -> Ticket:
        """Update the status of a ticket.

        :raises ValueError: if ticket not found
        """
        ticket = self.get_by_id(ticket_id)
        if ticket is None:
            msg = "Ticket not found"
            raise ValueError(msg)
        ticket.status = status
        self.session.add(ticket)
        self.session.commit()
        self.session.refresh(ticket)
        return ticket
