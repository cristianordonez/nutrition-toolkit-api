from __future__ import annotations

import typing

import pytest
from sqlmodel import Session, SQLModel, create_engine

from ntk.models.ticket import Ticket
from ntk.repositories.ticket_repo import TicketRepo

if typing.TYPE_CHECKING:
    from collections.abc import Generator


@pytest.fixture
def ticket_repo() -> Generator[TicketRepo, None, None]:
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield TicketRepo(session)


def test_ticket_repository_crud(ticket_repo: TicketRepo) -> None:
    first = ticket_repo.create(Ticket(title="First", created_by="dietitian"))
    second = ticket_repo.create(Ticket(title="Second", created_by="dietitian"))

    assert list(ticket_repo.list_all()) == [first, second]
    assert ticket_repo.get_by_id(first.ticket_id) == first

    message = ticket_repo.add_message(first.ticket_id, "Follow up", "reviewer")
    assert message.message_text == "Follow up"
    assert message.ticket_id == first.ticket_id

    updated = ticket_repo.update_status(first.ticket_id, "closed")
    assert updated.status == "closed"


def test_ticket_repository_rejects_missing_ticket(ticket_repo: TicketRepo) -> None:
    missing_id = Ticket(title="Missing", created_by="dietitian").ticket_id

    with pytest.raises(ValueError, match="Ticket not found"):
        ticket_repo.add_message(missing_id, "No ticket", "reviewer")
    with pytest.raises(ValueError, match="Ticket not found"):
        ticket_repo.update_status(missing_id, "closed")
