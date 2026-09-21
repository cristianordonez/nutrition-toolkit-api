"""Pick the on-device extraction model for this machine.

Extraction has to emit a twelve-way discriminated union across ~23 nested
definitions. A model too small for that does not fail loudly -- it returns
plausible-looking facts with the wrong discriminator or invented enum values,
which is worse than no extraction at all in a clinical tool. So the machine
picks the model by default, a user override is allowed for people who know
what they are doing, and machines that cannot host a capable-enough model are
refused outright rather than quietly producing bad data.

Sizes below are the quantized download sizes Ollama reports, and the RAM floors
assume the model shares unified memory with the OS and the app.
"""

from __future__ import annotations

import dataclasses
import os

#: Below this there is not enough memory for a model that can hold the
#: extraction schema, so local extraction is refused rather than degraded.
MINIMUM_RAM_GB = 16


@dataclasses.dataclass(frozen=True, slots=True)
class ModelTier:
    """One candidate model and the machine it needs."""

    model: str
    approximate_download_gb: float
    minimum_ram_gb: int


#: Smallest first. Picked as defaults to validate against real documents, not
#: as a claim that one family beats another at this task.
MODEL_TIERS: tuple[ModelTier, ...] = (
    ModelTier(model="qwen2.5:7b", approximate_download_gb=4.7, minimum_ram_gb=16),
    ModelTier(model="qwen2.5:14b", approximate_download_gb=9.0, minimum_ram_gb=24),
    ModelTier(model="qwen2.5:32b", approximate_download_gb=19.9, minimum_ram_gb=48),
)


class UnsupportedMachineError(RuntimeError):
    """Raised when this machine cannot host a capable-enough local model."""


def total_ram_gb() -> int:
    """Return installed physical memory in whole gigabytes."""
    total_bytes = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    return int(total_bytes / 1024**3)


def recommended_tier(ram_gb: int) -> ModelTier | None:
    """Return the largest tier this machine can host, or None if too small."""
    affordable = [tier for tier in MODEL_TIERS if ram_gb >= tier.minimum_ram_gb]
    return affordable[-1] if affordable else None


def resolve_model(
    *,
    override: str | None = None,
    ram_gb: int | None = None,
) -> str:
    """Return the model to run, honouring an override above the RAM floor.

    The floor is a property of the machine, not of the chosen model: an
    override lets someone run a different model, but not turn on local
    extraction where nothing capable can fit.
    """
    available_ram = total_ram_gb() if ram_gb is None else ram_gb
    if available_ram < MINIMUM_RAM_GB:
        message = (
            f"On-device extraction needs at least {MINIMUM_RAM_GB} GB of memory; "
            f"this machine has {available_ram} GB. Keep using the hosted model."
        )
        raise UnsupportedMachineError(message)
    if override:
        return override
    tier = recommended_tier(available_ram)
    if tier is None:  # pragma: no cover - unreachable while floor == smallest tier
        message = f"No local model tier fits {available_ram} GB."
        raise UnsupportedMachineError(message)
    return tier.model


__all__ = [
    "MINIMUM_RAM_GB",
    "MODEL_TIERS",
    "ModelTier",
    "UnsupportedMachineError",
    "recommended_tier",
    "resolve_model",
    "total_ram_gb",
]
