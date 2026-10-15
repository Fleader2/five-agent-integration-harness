"""Recursive Agent-4-Assisted Candidate Search Orchestration: the harness's own output
contract. Plain, frozen dataclasses -- consistent with ``app.harness.types`` -- holding
whatever Agent 2's own subprocess round-runner reports as a raw dict (``round_summary``, the
exact ``serialize_round_result`` shape) alongside this harness's own calibration-routing and
stopping-rule bookkeeping. The harness never imports Agent 2's own Python package (see
``app.harness.types``'s identical reasoning); it only ever reads the one documented dict shape
that round-runner writes.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class StoppingReason(StrEnum):
    """Why ``run_recursive_candidate_search`` stopped -- always reported, never left implicit
    (task instructions §6)."""

    #: ``OrchestrationPolicy.max_rounds`` reached.
    MAX_ROUNDS = "MAX_ROUNDS"
    #: ``OrchestrationPolicy.max_total_candidates`` reached (every candidate any round ever
    #: evaluated, cumulative).
    CANDIDATE_BUDGET_EXHAUSTED = "CANDIDATE_BUDGET_EXHAUSTED"
    #: ``CalibrationSelectionPolicy.total_calibration_run_budget`` reached.
    CALIBRATION_BUDGET_EXHAUSTED = "CALIBRATION_BUDGET_EXHAUSTED"
    #: The best candidate's own ``overall_score`` improved by less than
    #: ``OrchestrationPolicy.improvement_epsilon`` versus the previous round.
    NO_IMPROVEMENT = "NO_IMPROVEMENT"
    #: The retained candidate set's own structural identity (every ``module_ids`` partition)
    #: has not changed for two consecutive rounds.
    STABLE_BOUNDARY_CONVERGENCE = "STABLE_BOUNDARY_CONVERGENCE"
    #: The retained candidate *set* (by candidate id) is byte-identical to an earlier round --
    #: distinct from ``STABLE_BOUNDARY_CONVERGENCE`` (structural partitions unchanged, but
    #: candidate ids could still differ run to run); this checks the stronger, exact condition.
    REPEATED_CANDIDATE_SET = "REPEATED_CANDIDATE_SET"
    #: ``OrchestrationPolicy.require_human_review`` was set -- stopped after one round,
    #: returning a ranked/calibrated candidate set for a human to review before any further
    #: search/refinement (task instructions §7).
    HUMAN_REVIEW_GATE = "HUMAN_REVIEW_GATE"
    #: The underlying search produced nothing new to explore this round (every candidate was
    #: already seen, or the round's own ``retained`` set came back empty).
    SEARCH_EXHAUSTED = "SEARCH_EXHAUSTED"


class CalibrationRunOutcome(StrEnum):
    """What actually happened for one ``CALIBRATE`` decision this orchestration routed (or did
    not route) -- task instructions §4/§9."""

    #: A genuinely new Agent 3/Agent 4 round trip ran and succeeded (produced a disclosed
    #: outcome -- not necessarily a *positive* one; ``CALIBRATION_FAILED``/``UNIDENTIFIABLE``
    #: still count as a successful, real round trip).
    NEW_RUN_SUCCEEDED = "NEW_RUN_SUCCEEDED"
    #: An already-cached evaluation, keyed by this module's own stable identity, was reused
    #: instead of running Agent 3/Agent 4 again.
    REUSED_CACHED_EVIDENCE = "REUSED_CACHED_EVIDENCE"
    #: Agent 2 itself resolved this module as ``BOUNDARY_INADEQUATE`` locally -- no round trip
    #: was ever attempted.
    LOCALLY_RESOLVED = "LOCALLY_RESOLVED"
    #: The Agent 3/Agent 4 subprocess chain failed (an infrastructure/numerical defect, never a
    #: genuine calibration outcome) -- never cached, never counted as evidence.
    INFRASTRUCTURE_FAILURE = "INFRASTRUCTURE_FAILURE"
    #: No calibration dataset was available for this module (``calibration_request_provider``
    #: returned ``None``) -- never attempted, never fabricated.
    NO_DATASET_AVAILABLE = "NO_DATASET_AVAILABLE"


@dataclass(frozen=True, slots=True)
class OrchestrationPolicy:
    """Deterministic stopping-rule configuration for one ``run_recursive_candidate_search``
    call (task instructions §6)."""

    max_rounds: int
    max_total_candidates: int
    improvement_epsilon: str
    require_human_review: bool
    policy_version: str


@dataclass(frozen=True, slots=True)
class CalibrationRunRecord:
    """One module's own, fully-reasoned calibration-routing outcome this round -- always
    recorded (task instructions §9: a user must be able to reconstruct why one modularization
    outranked another)."""

    round_number: int
    candidate_id: str
    module_id: str
    cache_key: str | None
    outcome: CalibrationRunOutcome
    agent4_run_id: str | None
    reason: str


@dataclass(frozen=True, slots=True)
class RoundRecord:
    """Everything one round of the recursive loop produced."""

    round_number: int
    #: The exact dict ``app.agent2.candidate_orchestration.serialize_round_result`` produced
    #: for this round -- never re-typed Harness-side (this package never imports Agent 2's own
    #: Python package); every structural score/candidate/lineage/decision a user needs to
    #: reconstruct this round's own provenance is already in here verbatim.
    round_summary: dict[str, Any]
    calibration_runs: tuple[CalibrationRunRecord, ...]
    best_overall_score: str | None


@dataclass(frozen=True, slots=True)
class RecursiveCandidateSearchResult:
    """Everything one ``run_recursive_candidate_search`` call produces -- the full, cross-round
    provenance (task instructions §9): every round's own structural scores, every calibration
    run/reused-cache decision with its own Agent 4 run id, the policies in effect, and why the
    orchestration stopped."""

    orchestration_id: str
    model_id: str
    seed_modularization_id: str
    rounds: tuple[RoundRecord, ...]
    stopping_reason: StoppingReason
    requires_user_review: bool
    total_candidates_seen: int
    total_calibration_runs_used: int
    orchestration_policy: OrchestrationPolicy
    policy_version: str
    warnings: tuple[str, ...] = ()


__all__ = [
    "CalibrationRunOutcome",
    "CalibrationRunRecord",
    "OrchestrationPolicy",
    "RecursiveCandidateSearchResult",
    "RoundRecord",
    "StoppingReason",
]
