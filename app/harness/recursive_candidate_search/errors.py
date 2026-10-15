"""Recursive Agent-4-Assisted Candidate Search Orchestration: harness-side domain errors."""

from __future__ import annotations


class RecursiveCandidateSearchError(ValueError):
    """Base error for this package -- a malformed policy/request, or (see ``agent2_round.py``)
    an Agent 2 subprocess infrastructure failure -- never a disclosed scientific outcome
    (which is always a typed result, never an exception)."""


__all__ = ["RecursiveCandidateSearchError"]
