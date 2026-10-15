"""Recursive Agent-4-Assisted Candidate Search Orchestration: the harness's own half of
closing the modularization loop.

Drives Agent 2's own ``app.agent2.candidate_orchestration`` one bounded round at a time
(``agent2_round.invoke_agent2_candidate_search_round``, a real subprocess invocation of
``app/harness/runners/run_agent2_candidate_search_round.py``), routes whatever that round's own
calibration-selection gate selects through ``app.harness.module_calibration`` (unchanged) --
reusing cached evidence by stable identity (``cache.py``) wherever possible -- and decides, via
an explicit ``OrchestrationPolicy``, how many rounds to run and when to stop. Agent 2 never
calls Agent 3 or Agent 4; this package is the one, explicit routing point.

Public API: ``run_recursive_candidate_search`` (``orchestration``);
``invoke_agent2_candidate_search_round`` (``agent2_round``); ``cache_key_for``,
``FileCalibrationEvidenceCache`` (``cache``); every type (``types``);
``RecursiveCandidateSearchError`` (``errors``).
"""

from __future__ import annotations

from app.harness.recursive_candidate_search.agent2_round import invoke_agent2_candidate_search_round
from app.harness.recursive_candidate_search.cache import FileCalibrationEvidenceCache, cache_key_for
from app.harness.recursive_candidate_search.errors import RecursiveCandidateSearchError
from app.harness.recursive_candidate_search.orchestration import run_recursive_candidate_search
from app.harness.recursive_candidate_search.types import (
    CalibrationRunOutcome,
    CalibrationRunRecord,
    OrchestrationPolicy,
    RecursiveCandidateSearchResult,
    RoundRecord,
    StoppingReason,
)

__all__ = [
    "CalibrationRunOutcome",
    "CalibrationRunRecord",
    "FileCalibrationEvidenceCache",
    "OrchestrationPolicy",
    "RecursiveCandidateSearchError",
    "RecursiveCandidateSearchResult",
    "RoundRecord",
    "StoppingReason",
    "cache_key_for",
    "invoke_agent2_candidate_search_round",
    "run_recursive_candidate_search",
]
