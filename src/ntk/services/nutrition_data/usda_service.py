"""Backward-compatible imports for the USDA nutrition data service."""

from __future__ import annotations

from ntk.services.nutrition_data.usda import USDAService, USDASyncResult
from ntk.services.nutrition_data.usda_transformer import USDAResponseTransformer

__all__ = ["USDAResponseTransformer", "USDAService", "USDASyncResult"]
