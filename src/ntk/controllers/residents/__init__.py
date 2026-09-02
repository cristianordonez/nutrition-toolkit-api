"""Controllers for resident data operations."""

from __future__ import annotations

from .assessments import (
    ResidentAssessmentsController,
    ResidentAssessmentsOptions,
    ResidentAssessmentsResult,
)
from .clinical_facts import (
    ResidentClinicalFactsController,
    ResidentClinicalFactsOptions,
    ResidentClinicalFactsResult,
)
from .list import ResidentListController, ResidentListOptions, ResidentListResult
from .weights import (
    ResidentWeightsController,
    ResidentWeightsOptions,
    ResidentWeightsResult,
)

__all__ = [
    "ResidentAssessmentsController",
    "ResidentAssessmentsOptions",
    "ResidentAssessmentsResult",
    "ResidentClinicalFactsController",
    "ResidentClinicalFactsOptions",
    "ResidentClinicalFactsResult",
    "ResidentListController",
    "ResidentListOptions",
    "ResidentListResult",
    "ResidentWeightsController",
    "ResidentWeightsOptions",
    "ResidentWeightsResult",
]
