"""``run_hierarchical_recursive_modularization``: the harness's own second recursion
dimension -- depth into nested submodules -- built entirely on top of the existing, unchanged
``app.harness.recursive_candidate_search.run_recursive_candidate_search`` (one call per
hierarchy node) and Agent 2's own existing ``materialize_submodel``/``build_submodel``
(invoked, via ``--attach-modularization``/``--submodel-module-id``, exactly as it already is
for a single level -- never duplicated or reimplemented here; task instructions §1).

**How a child node reaches its own submodel.** Each node's own flat recursive search already
returns, in its final round's own ``round_summary``, every module's content-key pairs for
every retained candidate (via ``calibration_decisions``, which always carries exactly one
decision per module of every retained candidate, regardless of outcome). To descend into one
eligible module of the accepted candidate, this driver forwards that *exact, already-computed*
structure back to Agent 2 as ``attach_modularization`` -- never re-deriving or inventing
membership itself -- so the next level's own ``run_agent2_candidate_search_round.py`` call can
attach it and materialize a submodel from the named module, exactly like the flat case already
does for the model's own original seed modularization.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.harness.hierarchical_recursion.types import (
    HierarchicalRecursionPolicy,
    HierarchicalRecursionResult,
    HierarchyBranchStoppingReason,
    HierarchyNodeRecord,
)
from app.harness.recursive_candidate_search import (
    FileCalibrationEvidenceCache,
    OrchestrationPolicy,
    RecursiveCandidateSearchResult,
    StoppingReason,
    run_recursive_candidate_search,
)
from app.harness.version import HIERARCHICAL_RECURSION_POLICY_VERSION

RecursiveSearchRunner = Callable[..., RecursiveCandidateSearchResult]

#: Flat ``StoppingReason``s meaning "this node's own search converged without anything new to
#: explore further" -- accepted decomposition still stands, but descending into *its* own
#: children is pointless (task instructions §6: "stable boundaries").
_STABLE_FLAT_STOPPING_REASONS = frozenset(
    {StoppingReason.STABLE_BOUNDARY_CONVERGENCE, StoppingReason.REPEATED_CANDIDATE_SET}
)


def _reaction_count(content_key_pairs: list[list[str]]) -> int:
    return sum(1 for pair in content_key_pairs if pair[0] == "REACTION")


def _short_module_tag(module_id: str) -> str:
    """A short, deterministic, filesystem-safe stand-in for a (content-addressed, so
    potentially very long -- one token per member reaction/species/parameter) module id, used
    only in ``run_id``/``node_id`` strings this harness turns into filenames
    (``agent2_round.py``'s own ``stage_dir``-rooted artifact paths) -- never used for any
    lookup or comparison, which always uses the real ``module_id`` string itself."""
    return hashlib.sha256(module_id.encode("utf-8")).hexdigest()[:12]


def _module_content_keys(
    round_summary: dict[str, Any], candidate_id: str
) -> dict[str, list[list[str]]]:
    """``{module_id: content_key_pairs}`` for every module of ``candidate_id`` -- harvested
    from ``round_summary["calibration_decisions"]`` (see this module's own docstring); never
    re-derived or guessed here."""
    result: dict[str, list[list[str]]] = {}
    for decision in round_summary.get("calibration_decisions", []):
        if decision["candidate_id"] != candidate_id:
            continue
        result.setdefault(decision["module_id"], decision["content_key"])
    return result


def _best_scored(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    scored = [c for c in candidates if c.get("overall_score") is not None]
    if not scored:
        return None
    return max(scored, key=lambda c: Decimal(c["overall_score"]))


def run_hierarchical_recursive_modularization(
    *,
    agent1_view_path: str | Path,
    criteria_weights: dict[str, Any],
    search_policy: dict[str, Any],
    calibration_selection_policy: dict[str, Any],
    flat_orchestration_policy: OrchestrationPolicy,
    recursion_policy: HierarchicalRecursionPolicy,
    calibration_request_provider: Callable[..., dict[str, Any] | None],
    stage_dir: str | Path,
    correlation_id: str,
    run_id_prefix: str,
    functional_evaluation_selection_policy: dict[str, Any] | None = None,
    seed_modularization_id: str | None = None,
    exclude_single_module_from_ranking: bool = True,
    apply_resolution_correction: bool = False,
    build_request_path: str | Path | None = None,
    recursive_search_runner: RecursiveSearchRunner = run_recursive_candidate_search,
    cache: FileCalibrationEvidenceCache | None = None,
    functional_cache: FileCalibrationEvidenceCache | None = None,
    timeout_seconds: float = 300.0,
) -> HierarchicalRecursionResult:
    """Run the bounded hierarchy: one flat recursive search at the root, then -- for every
    module of its own accepted modularization eligible for subdivision (task instructions §3) --
    one flat recursive search on that module's own materialized submodel, recursing to bounded
    depth, with every budget tracked globally across the entire hierarchy (task instructions
    §5) and every node's own full provenance recorded (task instructions §4).

    A child decomposition is accepted only when its own best candidate's ``overall_score``
    improves on the degenerate ("leave the parent module intact") baseline's own score -- under
    the identical ``criteria_weights`` -- by at least
    ``recursion_policy.min_improvement_to_accept_child`` (task instructions §3). The root node
    has no such baseline (there is no parent to leave intact) and is always "accepted" once a
    genuine, non-degenerate candidate exists.

    ``cache``/``functional_cache`` (shared ``FileCalibrationEvidenceCache`` instances) are
    reused verbatim across every node/level -- a module whose own content happens to recur at a
    different hierarchy position reuses its evidence exactly like it already would across
    separate rounds of one flat search (task instructions §5); a cache hit never consumes
    either global budget (``run_recursive_candidate_search``'s own, unchanged discipline).
    """
    stage_dir = Path(stage_dir)
    cache = (
        cache
        if cache is not None
        else FileCalibrationEvidenceCache(stage_dir / "calibration_cache")
    )
    functional_cache = (
        functional_cache
        if functional_cache is not None
        else FileCalibrationEvidenceCache(stage_dir / "functional_evaluation_cache")
    )

    state = {"nodes": 0, "functional": 0, "calibration": 0, "root_model_id": ""}
    nodes: list[HierarchyNodeRecord] = []
    pending_review: list[dict[str, Any]] = []
    requires_user_review = {"value": False}
    warnings: list[str] = []

    def _record(
        *,
        node_id: str,
        depth: int,
        parent_modularization_id: str | None,
        parent_module_id: str | None,
        child_submodel_id: str | None,
        child_modularization_id: str | None,
        child_module_ids: tuple[str, ...],
        accepted: bool,
        reason: str,
        baseline_score: str | None,
        child_score: str | None,
        branch_stopping_reason: HierarchyBranchStoppingReason | None,
        recursive_search_stopping_reason: str,
        recursive_search_rounds: int,
        recursive_search_policy_version: str,
    ) -> None:
        nodes.append(
            HierarchyNodeRecord(
                node_id=node_id,
                depth=depth,
                root_model_id=state["root_model_id"],
                parent_modularization_id=parent_modularization_id,
                parent_module_id=parent_module_id,
                child_submodel_id=child_submodel_id,
                child_modularization_id=child_modularization_id,
                child_module_ids=child_module_ids,
                accepted=accepted,
                reason=reason,
                baseline_score=baseline_score,
                child_score=child_score,
                branch_stopping_reason=branch_stopping_reason,
                criteria_weights=criteria_weights,
                search_policy=search_policy,
                calibration_selection_policy=calibration_selection_policy,
                functional_evaluation_selection_policy=functional_evaluation_selection_policy,
                recursive_search_stopping_reason=recursive_search_stopping_reason,
                recursive_search_rounds=recursive_search_rounds,
                recursive_search_policy_version=recursive_search_policy_version,
            )
        )

    def _process_node(
        *,
        depth: int,
        parent_modularization_id: str | None,
        parent_module_id: str | None,
        attach_modularization: dict[str, Any] | None,
        submodel_module_id: str | None,
        run_id_suffix: str,
    ) -> None:
        parent_module_tag = _short_module_tag(parent_module_id) if parent_module_id else "root"
        node_id = f"node::depth{depth}::{parent_module_tag}::{uuid.uuid4().hex[:8]}"

        if state["nodes"] >= recursion_policy.max_total_hierarchy_nodes:
            _record(
                node_id=node_id,
                depth=depth,
                parent_modularization_id=parent_modularization_id,
                parent_module_id=parent_module_id,
                child_submodel_id=None,
                child_modularization_id=None,
                child_module_ids=(),
                accepted=False,
                reason="global max_total_hierarchy_nodes already reached",
                baseline_score=None,
                child_score=None,
                branch_stopping_reason=HierarchyBranchStoppingReason.MAX_HIERARCHY_NODES_EXHAUSTED,
                recursive_search_stopping_reason="",
                recursive_search_rounds=0,
                recursive_search_policy_version="",
            )
            return

        if depth > 0:
            functional_exhausted = (
                functional_evaluation_selection_policy is not None
                and state["functional"] >= recursion_policy.max_total_functional_evaluation_budget
            )
            calibration_exhausted = (
                state["calibration"] >= recursion_policy.max_total_calibration_budget
            )
            if functional_exhausted or calibration_exhausted:
                _record(
                    node_id=node_id,
                    depth=depth,
                    parent_modularization_id=parent_modularization_id,
                    parent_module_id=parent_module_id,
                    child_submodel_id=None,
                    child_modularization_id=None,
                    child_module_ids=(),
                    accepted=False,
                    reason="global functional/calibration budget already exhausted",
                    baseline_score=None,
                    child_score=None,
                    branch_stopping_reason=(
                        HierarchyBranchStoppingReason.FUNCTIONAL_EVALUATION_BUDGET_EXHAUSTED
                        if functional_exhausted
                        else HierarchyBranchStoppingReason.CALIBRATION_BUDGET_EXHAUSTED
                    ),
                    recursive_search_stopping_reason="",
                    recursive_search_rounds=0,
                    recursive_search_policy_version="",
                )
                return

        state["nodes"] += 1
        remaining_functional = max(
            0,
            recursion_policy.max_total_functional_evaluation_budget - state["functional"],
        )
        remaining_calibration = max(
            0, recursion_policy.max_total_calibration_budget - state["calibration"]
        )
        level_functional_policy = (
            dict(functional_evaluation_selection_policy)
            | {"total_functional_evaluation_budget": remaining_functional}
            if functional_evaluation_selection_policy is not None
            else None
        )
        level_calibration_policy = dict(calibration_selection_policy) | {
            "total_calibration_run_budget": remaining_calibration
        }

        result = recursive_search_runner(
            agent1_view_path=agent1_view_path,
            criteria_weights=criteria_weights,
            search_policy=search_policy,
            calibration_selection_policy=level_calibration_policy,
            orchestration_policy=flat_orchestration_policy,
            calibration_request_provider=calibration_request_provider,
            stage_dir=stage_dir,
            correlation_id=correlation_id,
            run_id_prefix=f"{run_id_prefix}::{run_id_suffix}",
            seed_modularization_id=seed_modularization_id if depth == 0 else None,
            submodel_module_id=submodel_module_id,
            # A child node's own acceptance rule (below) always compares its best candidate
            # against the degenerate, intact-parent baseline -- that baseline only exists when
            # degenerate candidates are actually tracked, so every depth > 0 level forces this
            # True regardless of the caller's own root-level choice (task instructions §3:
            # "respect existing... one-module reference-only behavior").
            exclude_single_module_from_ranking=(
                True if depth > 0 else exclude_single_module_from_ranking
            ),
            apply_resolution_correction=apply_resolution_correction,
            build_request_path=build_request_path,
            cache=cache,
            functional_evaluation_selection_policy=level_functional_policy,
            functional_cache=functional_cache,
            timeout_seconds=timeout_seconds,
            attach_modularization=attach_modularization,
        )
        state["functional"] += result.total_functional_evaluations_used
        state["calibration"] += result.total_calibration_runs_used
        if not state["root_model_id"]:
            state["root_model_id"] = result.model_id

        last_round = result.rounds[-1] if result.rounds else None
        round_summary = last_round.round_summary if last_round is not None else {}
        best = _best_scored(round_summary.get("retained", []))
        baseline = _best_scored(round_summary.get("degenerate", []))
        baseline_score = baseline["overall_score"] if baseline is not None else None

        if best is None:
            _record(
                node_id=node_id,
                depth=depth,
                parent_modularization_id=parent_modularization_id,
                parent_module_id=parent_module_id,
                child_submodel_id=round_summary.get("model_id"),
                child_modularization_id=None,
                child_module_ids=(),
                accepted=False,
                reason="recursive search never retained a genuine, non-degenerate candidate",
                baseline_score=baseline_score,
                child_score=None,
                branch_stopping_reason=HierarchyBranchStoppingReason.NO_VALID_CHILD_DECOMPOSITION,
                recursive_search_stopping_reason=result.stopping_reason.value,
                recursive_search_rounds=len(result.rounds),
                recursive_search_policy_version=result.policy_version,
            )
            return

        accepted = True
        reason = f"accepted: overall_score={best['overall_score']!r}"
        branch_stopping_reason: HierarchyBranchStoppingReason | None = None

        if depth > 0:
            if baseline_score is None:
                accepted = False
                reason = (
                    "no degenerate (intact-parent) baseline evidence available to compare against"
                )
                branch_stopping_reason = HierarchyBranchStoppingReason.INSUFFICIENT_EVIDENCE
            else:
                improvement = Decimal(best["overall_score"]) - Decimal(baseline_score)
                threshold = Decimal(recursion_policy.min_improvement_to_accept_child)
                if improvement < threshold:
                    accepted = False
                    reason = (
                        f"improvement {improvement} over intact-parent baseline "
                        f"{baseline_score} is below min_improvement_to_accept_child={threshold}"
                    )
                    branch_stopping_reason = HierarchyBranchStoppingReason.INSUFFICIENT_IMPROVEMENT
                else:
                    reason = (
                        f"accepted: overall_score={best['overall_score']} improves "
                        f"{improvement} over intact-parent baseline {baseline_score}"
                    )

        eligible_modules: list[str] = []
        too_small_modules: list[str] = []
        module_content_keys: dict[str, list[list[str]]] = {}
        should_descend = accepted

        if accepted:
            if result.stopping_reason in _STABLE_FLAT_STOPPING_REASONS:
                branch_stopping_reason = HierarchyBranchStoppingReason.STABLE_BOUNDARIES
                should_descend = False
            elif depth >= recursion_policy.max_depth:
                branch_stopping_reason = HierarchyBranchStoppingReason.MAX_DEPTH
                should_descend = False
            else:
                module_content_keys = _module_content_keys(round_summary, best["candidate_id"])
                for mid, pairs in sorted(module_content_keys.items()):
                    if _reaction_count(pairs) >= recursion_policy.min_reactions_per_module:
                        eligible_modules.append(mid)
                    else:
                        too_small_modules.append(mid)
                if not eligible_modules:
                    branch_stopping_reason = HierarchyBranchStoppingReason.NO_ELIGIBLE_MODULES
                    should_descend = False
                elif recursion_policy.require_human_review:
                    branch_stopping_reason = HierarchyBranchStoppingReason.HUMAN_REVIEW_GATE
                    should_descend = False
        else:
            should_descend = False

        _record(
            node_id=node_id,
            depth=depth,
            parent_modularization_id=parent_modularization_id,
            parent_module_id=parent_module_id,
            child_submodel_id=round_summary.get("model_id"),
            child_modularization_id=best["candidate_id"] if accepted else None,
            child_module_ids=tuple(best["module_ids"]) if accepted else (),
            accepted=accepted,
            reason=reason,
            baseline_score=baseline_score,
            child_score=best["overall_score"],
            branch_stopping_reason=branch_stopping_reason,
            recursive_search_stopping_reason=result.stopping_reason.value,
            recursive_search_rounds=len(result.rounds),
            recursive_search_policy_version=result.policy_version,
        )

        for mid in too_small_modules:
            too_small_tag = (
                f"node::depth{depth + 1}::{_short_module_tag(mid)}::{uuid.uuid4().hex[:8]}"
            )
            _record(
                node_id=too_small_tag,
                depth=depth + 1,
                parent_modularization_id=best["candidate_id"],
                parent_module_id=mid,
                child_submodel_id=None,
                child_modularization_id=None,
                child_module_ids=(),
                accepted=False,
                reason=(
                    f"{_reaction_count(module_content_keys[mid])} reaction(s) is below "
                    f"min_reactions_per_module={recursion_policy.min_reactions_per_module} -- "
                    "never attempted"
                ),
                baseline_score=None,
                child_score=None,
                branch_stopping_reason=HierarchyBranchStoppingReason.MODULE_TOO_SMALL,
                recursive_search_stopping_reason="",
                recursive_search_rounds=0,
                recursive_search_policy_version="",
            )

        if not should_descend:
            if branch_stopping_reason is HierarchyBranchStoppingReason.HUMAN_REVIEW_GATE:
                requires_user_review["value"] = True
                for mid in eligible_modules:
                    pending_review.append(
                        {
                            "parent_node_id": node_id,
                            "depth": depth + 1,
                            "parent_modularization_id": best["candidate_id"],
                            "module_id": mid,
                            "reaction_count": _reaction_count(module_content_keys[mid]),
                        }
                    )
            return

        attach_payload = {
            "modularization_id": best["candidate_id"],
            "module_ids": sorted(module_content_keys),
            "memberships": [
                {"module_id": mid, "component_type": pair[0], "component_id": pair[1]}
                for mid, pairs in module_content_keys.items()
                for pair in pairs
            ],
        }
        for mid in eligible_modules:
            if state["nodes"] >= recursion_policy.max_total_hierarchy_nodes:
                break
            _process_node(
                depth=depth + 1,
                parent_modularization_id=best["candidate_id"],
                parent_module_id=mid,
                attach_modularization=attach_payload,
                submodel_module_id=mid,
                run_id_suffix=f"d{depth + 1}::{_short_module_tag(mid)}",
            )

    _process_node(
        depth=0,
        parent_modularization_id=seed_modularization_id,
        parent_module_id=None,
        attach_modularization=None,
        submodel_module_id=None,
        run_id_suffix="d0",
    )

    return HierarchicalRecursionResult(
        hierarchy_id=f"hierarchical-recursion::{run_id_prefix}",
        root_model_id=state["root_model_id"],
        nodes=tuple(nodes),
        total_nodes_created=state["nodes"],
        total_functional_evaluations_used=state["functional"],
        total_calibration_runs_used=state["calibration"],
        requires_user_review=requires_user_review["value"],
        pending_review_modules=tuple(pending_review),
        recursion_policy=recursion_policy,
        policy_version=HIERARCHICAL_RECURSION_POLICY_VERSION,
        warnings=tuple(warnings),
    )


__all__ = ["run_hierarchical_recursive_modularization"]
