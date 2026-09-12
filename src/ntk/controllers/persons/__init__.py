"""Controllers for person data operations."""

from __future__ import annotations

from .assessments import (
    PersonAssessmentsController,
    PersonAssessmentsOptions,
    PersonAssessmentsResult,
)
from .clinical_facts import (
    PersonClinicalFactsController,
    PersonClinicalFactsOptions,
    PersonClinicalFactsResult,
)
from .list import PersonListController, PersonListOptions, PersonListResult
from .weights import (
    PersonWeightsController,
    PersonWeightsOptions,
    PersonWeightsResult,
)

__all__ = [
    "PersonAssessmentsController",
    "PersonAssessmentsOptions",
    "PersonAssessmentsResult",
    "PersonClinicalFactsController",
    "PersonClinicalFactsOptions",
    "PersonClinicalFactsResult",
    "PersonListController",
    "PersonListOptions",
    "PersonListResult",
    "PersonWeightsController",
    "PersonWeightsOptions",
    "PersonWeightsResult",
]
