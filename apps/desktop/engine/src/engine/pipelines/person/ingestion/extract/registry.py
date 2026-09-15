"""Explicit registration for concrete document extractors."""

from __future__ import annotations

import inspect
import typing

from .base import PersonExtractor

ExtractorT = typing.TypeVar("ExtractorT", bound=PersonExtractor)

EXTRACTOR_REGISTRY: dict[str, type[PersonExtractor]] = {}


def register_extractor(cls: type[ExtractorT]) -> type[ExtractorT]:
    """Register a concrete document extractor and return its class."""
    if not issubclass(cls, PersonExtractor):
        msg = f"{cls.__name__} must inherit from PersonExtractor"
        raise TypeError(msg)
    if inspect.isabstract(cls):
        msg = f"{cls.__name__} must implement all abstract extractor methods"
        raise TypeError(msg)
    if cls.__name__ in EXTRACTOR_REGISTRY:
        msg = f"Extractor '{cls.__name__}' is already registered"
        raise ValueError(msg)
    EXTRACTOR_REGISTRY[cls.__name__] = cls
    return cls
