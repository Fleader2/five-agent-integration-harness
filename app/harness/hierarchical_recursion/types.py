"""Automatic Hierarchical Recursive Modularization: the harness's own output contract. Plain,
frozen dataclasses -- consistent with ``app.harness.recursive_candidate_search.types``'s own
lighter convention (no ``__post_init__`` validation; this package's values are always this
harness's own, already-trusted bookkeeping, never a cross-process boundary needing defensive
parsing).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class HierarchyBranchStoppingReason(StrEnum):
    """Why one hierarchy branch stopped descending further -- always reported, never left
    implicit (task instructions §6). Distinct from ``app.harness.recursive_candidate_search
    .types.StoppingReason``, which names why one *flat* recursive-search call (one hierarchy
    node's own level) stopped; a node can reach any flat ``StoppingReason`` internally and
    still be *accepted*, continuing the hierarchy -- these values are about the hierarchy's own
    decision to descend further or not."""

    #: ``HierarchicalRecursionPolicy.max_depth`` reached.
    MAX_DEPTH = "MAX_DEPTH"
    #: The module has fewer than ``HierarchicalRecursionPolicy.min_reactions_per_module``
    #: internal reactions -- never subdivided (task instructions §3: "a module should be
    #: eligible for recursion only if it is large enough").
    MODULE_TOO_SMALL = "MODULE_TOO_SMALL"
    #: The accepted modularization at this node has zero modules eligible for further
    #: subdivision (every one is too small, or none exist at all).
    NO_ELIGIBLE_MODULES = "NO_ELIGIBLE_MODULES"
    #: The recursive search on the materialized submodel never retained a genuine, non-
    #: degenerate candidate (every proposal was degenerate, or the search itself produced
    #: nothing new) -- there is no child decomposition to even consider accepting.
    NO_VALID_CHILD_DECOMPOSITION = "NO_VALID_CHILD_DECOMPOSITION"
    #: The best child decomposition's own ``overall_score`` did not exceed the degenerate
    #: (single-module, "leave the parent module intact") baseline by at least
    #: ``HierarchicalRecursionPolicy.min_improvement_to_accept_child`` (task instructions §3:
    #: "accept a child modularization only when it improves ... relative to leaving the parent
    #: module intact").
    INSUFFICIENT_IMPROVEMENT = "INSUFFICIENT_IMPROVEMENT"
    #: The child-level recursive search itself converged (``StoppingReason
    #: .STABLE_BOUNDARY_CONVERGENCE``/``.REPEATED_CANDIDATE_SET``) -- the decomposition found is
    #: still accepted if it independently clears ``min_improvement_to_accept_child``, but no
    #: further descent into *its own* children is attempted this call.
    STABLE_BOUNDARIES = "STABLE_BOUNDARIES"
    #: ``HierarchicalRecursionPolicy.max_total_hierarchy_nodes`` reached (global, across the
    #: whole hierarchy -- never reset per branch).
    MAX_HIERARCHY_NODES_EXHAUSTED = "MAX_HIERARCHY_NODES_EXHAUSTED"
    #: The global functional-evaluation budget
    #: (``HierarchicalRecursionPolicy.max_total_functional_evaluation_budget``) was already
    #: exhausted by an earlier node before this one could even attempt a real Agent 3 round
    #: trip.
    FUNCTIONAL_EVALUATION_BUDGET_EXHAUSTED = "FUNCTIONAL_EVALUATION_BUDGET_EXHAUSTED"
    #: The global calibration budget (``HierarchicalRecursionPolicy
    #: .max_total_calibration_budget``) was already exhausted by an earlier node.
    CALIBRATION_BUDGET_EXHAUSTED = "CALIBRATION_BUDGET_EXHAUSTED"
    #: The child-level search never obtained real, available ``DYNAMIC_ISOLATION``/
    #: ``SENSITIVITY_COHERENCE``/``CALIBRATION_INDEPENDENCE`` evidence for any retained
    #: candidate (every attempt resolved locally as unavailable, e.g.
    #: ``INSUFFICIENT_TARGETS``/``UNSUPPORTED_ANALYSIS``/``BOUNDARY_INADEQUATE``) -- there is
    #: real structural information, but no evidence-backed basis to prefer the decomposition
    #: over the intact parent.
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    #: ``HierarchicalRecursionPolicy.require_human_review`` was set -- the hierarchy paused
    #: after this node's own acceptance, returning the eligible-for-subdivision module list for
    #: review before any descent into them is attempted (task instructions §7).
    HUMAN_REVIEW_GATE = "HUMAN_REVIEW_GATE"


@dataclass(frozen=True, slots=True)
class HierarchicalRecursionPolicy:
    """Deterministic descent-policy configuration for one
    ``run_hierarchical_recursive_modularization`` call (task instructions §2)."""

    max_depth: int
    min_reactions_per_module: int
    max_total_hierarchy_nodes: int
    max_total_functional_evaluation_budget: int
    max_total_calibration_budget: int
    #: A ``Decimal``-parseable string, mirroring ``OrchestrationPolicy.improvement_epsilon``'s
    #: own convention exactly.
    min_improvement_to_accept_child: str
    require_human_review: bool
    policy_version: str


@dataclass(frozen=True, slots=True)
class HierarchyNodeRecord:
    """One node's own complete, reconstructable provenance (task instructions §4): the exact
    parent/child modularization and module ids, the depth, the acceptance decision and why, the
    scores/evidence in effect at decision time, and every policy/weight that produced it."""

    node_id: str
    depth: int
    root_model_id: str
    #: ``None`` only for the root node (depth 0), which has no parent module being subdivided.
    parent_modularization_id: str | None
    parent_module_id: str | None
    #: The materialized submodel's own content-addressed ``model_id`` this node searched --
    #: ``None`` for the root node, which searches the whole canonical model directly.
    child_submodel_id: str | None
    #: The accepted candidate's own modularization id at this node -- ``None`` when no child
    #: decomposition was accepted (``accepted=False``).
    child_modularization_id: str | None
    #: The accepted candidate's own module ids (content-addressed) -- ``()`` when not accepted.
    child_module_ids: tuple[str, ...]
    accepted: bool
    reason: str
    #: The degenerate ("leave the parent module intact") baseline's own ``overall_score`` under
    #: the weights in effect, as a string -- ``None`` when no degenerate baseline was available
    #: (the root node has no such baseline at all: there is no "parent" to leave intact).
    baseline_score: str | None
    #: The accepted (or best-attempted) child candidate's own ``overall_score``, as a string --
    #: ``None`` when no candidate was ever scored.
    child_score: str | None
    branch_stopping_reason: HierarchyBranchStoppingReason | None
    criteria_weights: dict[str, Any]
    search_policy: dict[str, Any]
    calibration_selection_policy: dict[str, Any]
    functional_evaluation_selection_policy: dict[str, Any] | None
    recursive_search_stopping_reason: str
    recursive_search_rounds: int
    recursive_search_policy_version: str


@dataclass(frozen=True, slots=True)
class HierarchicalRecursionResult:
    """Everything one ``run_hierarchical_recursive_modularization`` call produces -- the full,
    cross-node provenance (task instructions §4/§9): every node's own acceptance decision,
    global budget usage, and why each branch stopped."""

    hierarchy_id: str
    root_model_id: str
    nodes: tuple[HierarchyNodeRecord, ...]
    total_nodes_created: int
    total_functional_evaluations_used: int
    total_calibration_runs_used: int
    requires_user_review: bool
    #: Populated only when ``requires_user_review`` is ``True`` (task instructions §7): one
    #: entry per eligible-for-subdivision module the hierarchy has not yet descended into,
    #: naming the parent node/modularization/module and its own reaction count.
    pending_review_modules: tuple[dict[str, Any], ...]
    recursion_policy: HierarchicalRecursionPolicy
    policy_version: str
    warnings: tuple[str, ...] = ()


__all__ = [
    "HierarchicalRecursionPolicy",
    "HierarchicalRecursionResult",
    "HierarchyBranchStoppingReason",
    "HierarchyNodeRecord",
]
