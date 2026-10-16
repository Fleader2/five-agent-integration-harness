"""Automatic Hierarchical Recursive Modularization: domain errors."""

from __future__ import annotations


class HierarchicalRecursionError(ValueError):
    """Base error for this package -- a malformed policy/request, or (via
    ``run_recursive_candidate_search``) an Agent 2 subprocess infrastructure failure -- never a
    disclosed scientific outcome (which is always a typed result, never an exception)."""


__all__ = ["HierarchicalRecursionError"]
