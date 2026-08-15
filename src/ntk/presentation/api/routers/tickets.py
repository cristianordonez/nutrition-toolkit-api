from __future__ import annotations

import typing
from uuid import UUID  # noqa: TC003

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from ntk.database.db import get_session
from ntk.models import Ticket, TicketMessage, TicketPublic
from ntk.repositories.ticket_repo import TicketRepo

if typing.TYPE_CHECKING:
    from collections.abc import Sequence

router = APIRouter()


class CreateTicketRequest(BaseModel):
    title: str
    created_by: str
    status: str | None = None


class AddMessageRequest(BaseModel):
    message_text: str
    author: str


class UpdateStatusRequest(BaseModel):
    status: str


@router.get("/tickets/", response_model=list[Ticket])
async def list_tickets() -> Sequence[Ticket]:
    """List tickets.

    :return: All tickets
    """
    session = next(get_session())
    repo = TicketRepo(session)
    return repo.list_all()


@router.get("/tickets/{ticket_id}", response_model=TicketPublic)
async def get_ticket(ticket_id: UUID) -> Ticket:
    """Get ticket.

    :param ticket_id: id
    :raises HTTPException: HTTP exception
    :return: Ticket
    """
    session = next(get_session())
    repo = TicketRepo(session)
    ticket = repo.get_by_id(ticket_id)
    if ticket is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket not found",
        )
    return ticket


@router.post("/tickets/", response_model=Ticket, status_code=status.HTTP_201_CREATED)
async def create_ticket(payload: CreateTicketRequest) -> Ticket:
    """Create ticket.

    :param payload: create ticket payload
    :return: Ticket
    """
    session = next(get_session())
    repo = TicketRepo(session)
    ticket = Ticket(
        title=payload.title,
        created_by=payload.created_by,
        status=payload.status or "open",
    )
    return repo.create(ticket)


@router.post(
    "/tickets/{ticket_id}/messages",
    response_model=TicketMessage,
    status_code=status.HTTP_201_CREATED,
)
async def add_ticket_message(
    ticket_id: UUID,
    payload: AddMessageRequest,
) -> TicketMessage:
    """Add message to ticket.

    :param ticket_id: id
    :param payload: message string
    :raises HTTPException: HTTP Exception
    :return: TicketMessage
    """
    session = next(get_session())
    repo = TicketRepo(session)
    try:
        return repo.add_message(ticket_id, payload.message_text, payload.author)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket not found",
        ) from err


@router.patch("/tickets/{ticket_id}/status", response_model=Ticket)
async def update_ticket_status(ticket_id: UUID, payload: UpdateStatusRequest) -> Ticket:
    """Update ticket status.

    :param ticket_id: id
    :param payload: ticket status
    :raises HTTPException: HTTP exception
    :return: Ticket model
    """
    session = next(get_session())
    repo = TicketRepo(session)
    try:
        return repo.update_status(ticket_id, payload.status)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket not found",
        ) from err
