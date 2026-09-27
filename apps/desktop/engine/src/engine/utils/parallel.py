"""Small pool-based parallel execution helpers."""

from __future__ import annotations

import os
import typing
from enum import StrEnum
from multiprocessing import Pool
from multiprocessing.pool import ThreadPool

if typing.TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator
    from types import TracebackType

_InputT = typing.TypeVar("_InputT")
_ResultT = typing.TypeVar("_ResultT")


class _PoolProtocol(typing.Protocol):
    def map(
        self,
        function: Callable[[_InputT], _ResultT],
        values: Iterable[_InputT],
        chunksize: int | None = None,
    ) -> list[_ResultT]: ...

    def starmap(
        self,
        function: Callable[..., _ResultT],
        values: Iterable[tuple[typing.Any, ...]],
        chunksize: int | None = None,
    ) -> list[_ResultT]: ...

    def imap_unordered(
        self,
        function: Callable[[_InputT], _ResultT],
        values: Iterable[_InputT],
        chunksize: int = 1,
    ) -> Iterator[_ResultT]: ...

    def close(self) -> None: ...

    def terminate(self) -> None: ...

    def join(self) -> None: ...


class PoolMode(StrEnum):
    """Supported pool execution strategies."""

    PROCESS = "process"
    THREAD = "thread"


class ParallelPoolHandler:
    """Run generic callables in a managed process or thread pool."""

    def __init__(
        self,
        mode: PoolMode | str = PoolMode.THREAD,
        workers: int | None = None,
    ) -> None:
        """Configure the pool without starting workers until it is used."""
        try:
            self.mode = PoolMode(mode)
        except ValueError as error:
            valid_modes = ", ".join(mode.value for mode in PoolMode)
            msg = f"Invalid pool mode {mode!r}; expected one of: {valid_modes}"
            raise ValueError(msg) from error
        self.workers = workers if workers is not None else (os.cpu_count() or 1)
        if self.workers < 1:
            msg = "workers must be at least 1"
            raise ValueError(msg)
        self._pool: _PoolProtocol | None = None

    def __enter__(self) -> typing.Self:
        """Start and retain a pool for multiple operations."""
        if self._pool is not None:
            msg = "ParallelPoolHandler is already active"
            raise RuntimeError(msg)
        self._pool = self._create_pool()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close successful pools and terminate pools after an exception."""
        del exc_value, traceback
        if self._pool is None:
            return
        if exc_type is None:
            self._pool.close()
        else:
            self._pool.terminate()
        self._pool.join()
        self._pool = None

    def map(
        self,
        function: Callable[[_InputT], _ResultT],
        values: Iterable[_InputT],
        chunksize: int | None = None,
    ) -> list[_ResultT]:
        """Apply one callable to each input while preserving input order."""
        if self._pool is not None:
            return self._pool.map(function, values, chunksize)
        with self:
            pool = typing.cast("_PoolProtocol", self._pool)
            return pool.map(function, values, chunksize)

    def starmap(
        self,
        function: Callable[..., _ResultT],
        values: Iterable[tuple[typing.Any, ...]],
        chunksize: int | None = None,
    ) -> list[_ResultT]:
        """Apply arguments from each input tuple while preserving order."""
        if self._pool is not None:
            return self._pool.starmap(function, values, chunksize)
        with self:
            pool = typing.cast("_PoolProtocol", self._pool)
            return pool.starmap(function, values, chunksize)

    def imap_unordered(
        self,
        function: Callable[[_InputT], _ResultT],
        values: Iterable[_InputT],
        chunksize: int = 1,
    ) -> Iterator[_ResultT]:
        """Yield results as workers complete them without preserving order."""
        if self._pool is not None:
            yield from self._pool.imap_unordered(function, values, chunksize)
            return
        with self:
            pool = typing.cast("_PoolProtocol", self._pool)
            yield from pool.imap_unordered(function, values, chunksize)

    def _create_pool(self) -> _PoolProtocol:
        pool_type = Pool if self.mode is PoolMode.PROCESS else ThreadPool
        return typing.cast("_PoolProtocol", pool_type(processes=self.workers))


__all__ = ["ParallelPoolHandler", "PoolMode"]
