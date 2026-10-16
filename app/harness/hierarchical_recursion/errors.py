"""Automatic Hierarchical Recursive Modularization: domain errors."""

from __future__ import annotations


class HierarchicalRecursionError(ValueError):
    """Base error for this package -- a malformed policy/request, or (via
    ``run_recursive_candidate_search``) an Agent 2 subprocess infrastructure failure -- never a
    disclosed scientific outcome (which is always a typed result, never an exception)."""


class HierarchicalRecursionCheckpointError(HierarchicalRecursionError):
    """Raised by ``resume_hierarchical_recursive_modularization`` for a malformed, version-
    mismatched/stale, or decision-incomplete checkpoint -- never for a disclosed scientific
    outcome. A caller must fix the checkpoint/decisions and retry; never silently repaired or
    guessed here."""


__all__ = ["HierarchicalRecursionCheckpointError", "HierarchicalRecursionError"]
