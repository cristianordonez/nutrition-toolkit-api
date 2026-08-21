"""Repositories are called on by controllers to retrieve data."""

from __future__ import annotations

from .document_repo import DocumentRepo
from .ticket_repo import TicketRepo

__all__ = [
    "DocumentRepo",
    "TicketRepo",
]
