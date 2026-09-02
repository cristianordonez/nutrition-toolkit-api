from __future__ import annotations

import pytest

from ntk.utils.parallel import ParallelPoolHandler, PoolMode


def _square(value: int) -> int:
    return value * value


def _add(left: int, right: int) -> int:
    return left + right


def _raise_for_two(value: int) -> int:
    if value == 2:  # noqa: PLR2004
        msg = "worker failed"
        raise RuntimeError(msg)
    return value


@pytest.mark.parametrize("mode", [PoolMode.PROCESS, PoolMode.THREAD])
def test_map_supports_process_and_thread_modes(mode: PoolMode) -> None:
    handler = ParallelPoolHandler(mode=mode, workers=2)

    assert handler.map(_square, [1, 2, 3]) == [1, 4, 9]


@pytest.mark.parametrize("mode", [PoolMode.PROCESS, PoolMode.THREAD])
def test_starmap_supports_process_and_thread_modes(mode: PoolMode) -> None:
    with ParallelPoolHandler(mode=mode, workers=2) as handler:
        results = handler.starmap(_add, [(1, 2), (3, 4)])

    assert results == [3, 7]


def test_configured_worker_count_is_retained() -> None:
    handler = ParallelPoolHandler(mode=PoolMode.PROCESS, workers=3)

    assert handler.workers == 3  # noqa: PLR2004


def test_invalid_mode_is_rejected() -> None:
    with pytest.raises(ValueError, match="Invalid pool mode"):
        ParallelPoolHandler(mode="invalid")


@pytest.mark.parametrize("mode", [PoolMode.PROCESS, PoolMode.THREAD])
def test_worker_exceptions_propagate(mode: PoolMode) -> None:
    handler = ParallelPoolHandler(mode=mode, workers=2)

    with pytest.raises(RuntimeError, match="worker failed"):
        handler.map(_raise_for_two, [1, 2, 3])
