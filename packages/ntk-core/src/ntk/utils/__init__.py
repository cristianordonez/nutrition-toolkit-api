"""Dependency-free utilities genuinely used by both the cloud-api and engine apps.

A utility belongs here only while both apps actually import it (directly, or
transitively through another shared ntk-core module they both exercise, like
`ntk.calculators.nutrition_calculator` importing `Convert`). Engine-only or
cloud-only utilities live in that app's own `utils/` package instead.
"""

from __future__ import annotations
