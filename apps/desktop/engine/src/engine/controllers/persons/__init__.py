"""Controllers for person data operations."""

from __future__ import annotations

from .clinical_facts import (
    PersonClinicalFactsController,
    PersonClinicalFactsOptions,
    PersonClinicalFactsResult,
)
from .list import PersonListController, PersonListOptions, PersonListResult
from .ncps import (
    PersonNCPsController,
    PersonNCPsOptions,
    PersonNCPsResult,
)
from .summary import PersonSummaryController, PersonSummaryOptions
from .weights import (
    PersonWeightsController,
    PersonWeightsOptions,
    PersonWeightsResult,
)

__all__ = [
    "PersonClinicalFactsController",
    "PersonClinicalFactsOptions",
    "PersonClinicalFactsResult",
    "PersonListController",
    "PersonListOptions",
    "PersonListResult",
    "PersonNCPsController",
    "PersonNCPsOptions",
    "PersonNCPsResult",
    "PersonSummaryController",
    "PersonSummaryOptions",
    "PersonWeightsController",
    "PersonWeightsOptions",
    "PersonWeightsResult",
]
