"""Repositories are called on by controllers to retrieve data."""

from __future__ import annotations

from .ticket_repo import TicketRepo

__all__ = [
    "TicketRepo",
]
