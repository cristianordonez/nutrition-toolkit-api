"""Exercise the real embedding service with empty caches and network tripwires.

Run this in its own process, using the engine installation being verified.
It never opens a patient database or sends patient data anywhere.
"""

# ruff: noqa: INP001, PLC0415, S101, T201 - standalone verification command

from __future__ import annotations

import asyncio
import json
import math
import multiprocessing
import os
import pathlib
import sys
import tempfile
import typing

_TOLERANCE = 1e-6


def verify() -> None:
    """Verify first-load and repeated query/document inference with no network."""
    attempts: list[str] = []

    def block_http(*_args: object, **_kwargs: object) -> typing.NoReturn:
        attempts.append("httpx.send")
        msg = "Embedding attempted HTTP access"
        raise AssertionError(msg)

    def block_socket(event: str, _args: tuple[object, ...]) -> None:
        if event in {"socket.connect", "socket.getaddrinfo", "socket.gethostbyname"}:
            attempts.append(event)
            msg = "Embedding attempted socket access"
            raise AssertionError(msg)

    with tempfile.TemporaryDirectory(prefix="minilm-offline-") as temporary:
        for variable in (
            "HF_HOME",
            "HF_HUB_CACHE",
            "HUGGINGFACE_HUB_CACHE",
            "TRANSFORMERS_CACHE",
            "SENTENCE_TRANSFORMERS_HOME",
        ):
            os.environ[variable] = str(pathlib.Path(temporary) / variable)
        # Do NOT rely on these switches: local_files_only must suffice itself.
        os.environ.pop("HF_HUB_OFFLINE", None)
        os.environ.pop("TRANSFORMERS_OFFLINE", None)
        sys.addaudithook(block_socket)

        import httpx

        httpx.Client.send = block_http
        httpx.AsyncClient.send = block_http

        from sqlmodel import Session

        from engine.database.vectors import EMBEDDING_DIMENSIONS, EMBEDDING_MODEL
        from engine.paths import bundled_embedding_model_dir
        from engine.services import embedding_service

        with Session() as session:
            service = embedding_service.EmbeddingService(session)
            text = "Nutrition reference: protein and energy requirements."
            document = service.get_embedding(text)
            model = embedding_service._SHARED_MODEL  # noqa: SLF001
            query = service._embed_query(text)  # noqa: SLF001
            repeated = asyncio.run(
                embedding_service.EmbeddingService(session).get_embedding_async(text),
            )
            assert model is embedding_service._SHARED_MODEL  # noqa: SLF001
            assert service.model == EMBEDDING_MODEL
            assert len(document) == len(query) == EMBEDDING_DIMENSIONS
            assert all(math.isfinite(value) for value in document + query)
            assert math.isclose(
                math.sqrt(sum(x * x for x in document)),
                1,
                abs_tol=1e-5,
            )
            assert (
                max(abs(a - b) for a, b in zip(document, repeated, strict=True))
                < _TOLERANCE
            )
            assert (
                max(abs(a - b) for a, b in zip(document, query, strict=True))
                < _TOLERANCE
            )
            assert not attempts, attempts
            assert not any(pathlib.Path(temporary).rglob("*.safetensors"))
            print(
                json.dumps(
                    {
                        "model_path": str(bundled_embedding_model_dir()),
                        "dimensions": len(document),
                        "network_attempts": attempts,
                        "shared_model": True,
                    },
                ),
            )


if __name__ == "__main__":
    # Also usable as a frozen probe: dispatch multiprocessing helper processes
    # before any ML imports rather than running the verification again in them.
    multiprocessing.freeze_support()
    verify()
