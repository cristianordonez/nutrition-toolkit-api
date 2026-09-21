from __future__ import annotations

import pytest

from engine.services.local_model import (
    MINIMUM_RAM_GB,
    MODEL_TIERS,
    UnsupportedMachineError,
    recommended_tier,
    resolve_model,
    total_ram_gb,
)


def test_total_ram_reports_a_plausible_size() -> None:
    assert total_ram_gb() >= 1


@pytest.mark.parametrize(
    ("ram_gb", "expected"),
    [
        (8, None),
        (16, "qwen2.5:7b"),
        (24, "qwen2.5:14b"),
        (32, "qwen2.5:14b"),
        (48, "qwen2.5:32b"),
        (128, "qwen2.5:32b"),
    ],
)
def test_recommended_tier_scales_with_memory(ram_gb: int, expected: str | None) -> None:
    tier = recommended_tier(ram_gb)
    assert (tier.model if tier else None) == expected


def test_tiers_are_ordered_and_never_exceed_their_machine() -> None:
    floors = [tier.minimum_ram_gb for tier in MODEL_TIERS]
    assert floors == sorted(floors)
    for tier in MODEL_TIERS:
        # A model whose download alone rivals installed memory cannot be served
        # alongside the OS and the app.
        assert tier.approximate_download_gb < tier.minimum_ram_gb


def test_resolve_refuses_a_machine_below_the_floor() -> None:
    with pytest.raises(UnsupportedMachineError, match="at least 16 GB"):
        resolve_model(ram_gb=8)


def test_override_still_cannot_bypass_the_floor() -> None:
    with pytest.raises(UnsupportedMachineError):
        resolve_model(override="qwen2.5:0.5b", ram_gb=8)


def test_override_wins_on_a_supported_machine() -> None:
    assert resolve_model(override="llama3.1:8b", ram_gb=64) == "llama3.1:8b"


def test_auto_selection_matches_the_tier_for_this_machine() -> None:
    assert resolve_model(ram_gb=24) == "qwen2.5:14b"
    assert MODEL_TIERS[0].minimum_ram_gb == MINIMUM_RAM_GB
