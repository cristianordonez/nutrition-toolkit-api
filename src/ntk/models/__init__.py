"""Contains all pydantic models and dataclasses."""

from __future__ import annotations

from .api_key import APIKey, APIKeyPermission, Permission
from .document import (
    ChunkType,
    Document,
    DocumentChunk,
    DocumentEmbedding,
    DocumentType,
    StoredDocumentType,
)
from .rag import RagSearchMatch
from .ticket import Ticket, TicketMessage, TicketMessagePublic, TicketPublic

__all__: list[str] = [
    "APIKey",
    "APIKeyPermission",
    "ChunkType",
    "Document",
    "DocumentChunk",
    "DocumentEmbedding",
    "DocumentType",
    "Permission",
    "RagSearchMatch",
    "StoredDocumentType",
    "Ticket",
    "TicketMessage",
    "TicketMessagePublic",
    "TicketPublic",
]
