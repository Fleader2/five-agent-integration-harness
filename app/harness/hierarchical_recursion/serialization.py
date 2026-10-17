"""Plain-dict (de)serialization for ``HierarchyCheckpoint`` -- the one, documented way a
caller persists a paused hierarchical-recursion run and later reloads it for
``resume_hierarchical_recursive_modularization`` (human-review/resume increment, task
instructions §1).

Mirrors every other (de)serialization boundary in this project's family: a plain, JSON-ready
dict in, a fully-typed dataclass out, raising only for a genuinely malformed/incomplete
structure (``KeyError``/``TypeError``/``ValueError``) -- never silently filling in a guessed
default for a missing required field.
"""

from __future__ import annotations

from typing import Any

from app.harness.hierarchical_recursion.types import (
    HierarchicalRecursionPolicy,
    HierarchyBranchStoppingReason,
    HierarchyCheckpoint,
    HierarchyNodeRecord,
)
from app.harness.recursive_candidate_search import OrchestrationPolicy


def serialize_node_record(node: HierarchyNodeRecord) -> dict[str, Any]:
    """One ``HierarchyNodeRecord`` -> a plain, JSON-ready dict -- the exact inverse of
    ``deserialize_node_record``."""
    return {
        "node_id": node.node_id,
        "depth": node.depth,
        "root_model_id": node.root_model_id,
        "parent_modularization_id": node.parent_modularization_id,
        "parent_module_id": node.parent_module_id,
        "child_submodel_id": node.child_submodel_id,
        "child_modularization_id": node.child_modularization_id,
        "child_module_ids": list(node.child_module_ids),
        "accepted": node.accepted,
        "reason": node.reason,
        "baseline_score": node.baseline_score,
        "child_score": node.child_score,
        "branch_stopping_reason": (
            node.branch_stopping_reason.value if node.branch_stopping_reason is not None else None
        ),
        "criteria_weights": dict(node.criteria_weights),
        "search_policy": dict(node.search_policy),
        "calibration_selection_policy": dict(node.calibration_selection_policy),
        "functional_evaluation_selection_policy": (
            dict(node.functional_evaluation_selection_policy)
            if node.functional_evaluation_selection_policy is not None
            else None
        ),
        "recursive_search_stopping_reason": node.recursive_search_stopping_reason,
        "recursive_search_rounds": node.recursive_search_rounds,
        "recursive_search_policy_version": node.recursive_search_policy_version,
        "attach_payload": node.attach_payload,
    }


def deserialize_node_record(data: dict[str, Any]) -> HierarchyNodeRecord:
    """The exact inverse of ``serialize_node_record``. Raises ``KeyError``/``TypeError``/
    ``ValueError`` for a malformed entry -- never guesses a missing required field."""
    branch_reason = data["branch_stopping_reason"]
    return HierarchyNodeRecord(
        node_id=data["node_id"],
        depth=data["depth"],
        root_model_id=data["root_model_id"],
        parent_modularization_id=data["parent_modularization_id"],
        parent_module_id=data["parent_module_id"],
        child_submodel_id=data["child_submodel_id"],
        child_modularization_id=data["child_modularization_id"],
        child_module_ids=tuple(data["child_module_ids"]),
        accepted=bool(data["accepted"]),
        reason=data["reason"],
        baseline_score=data["baseline_score"],
        child_score=data["child_score"],
        branch_stopping_reason=(
            HierarchyBranchStoppingReason(branch_reason) if branch_reason is not None else None
        ),
        criteria_weights=dict(data["criteria_weights"]),
        search_policy=dict(data["search_policy"]),
        calibration_selection_policy=dict(data["calibration_selection_policy"]),
        functional_evaluation_selection_policy=(
            dict(data["functional_evaluation_selection_policy"])
            if data.get("functional_evaluation_selection_policy") is not None
            else None
        ),
        recursive_search_stopping_reason=data["recursive_search_stopping_reason"],
        recursive_search_rounds=data["recursive_search_rounds"],
        recursive_search_policy_version=data["recursive_search_policy_version"],
        attach_payload=data.get("attach_payload"),
    )


def serialize_checkpoint(checkpoint: HierarchyCheckpoint) -> dict[str, Any]:
    """One ``HierarchyCheckpoint`` -> a plain, JSON-ready dict -- the one documented shape a
    caller writes to disk/a database and later reloads via ``deserialize_checkpoint``."""
    return {
        "checkpoint_version": checkpoint.checkpoint_version,
        "hierarchy_id": checkpoint.hierarchy_id,
        "root_model_id": checkpoint.root_model_id,
        "run_id_prefix": checkpoint.run_id_prefix,
        "correlation_id": checkpoint.correlation_id,
        "agent1_view_path": checkpoint.agent1_view_path,
        "stage_dir": checkpoint.stage_dir,
        "seed_modularization_id": checkpoint.seed_modularization_id,
        "exclude_single_module_from_ranking": checkpoint.exclude_single_module_from_ranking,
        "apply_resolution_correction": checkpoint.apply_resolution_correction,
        "build_request_path": checkpoint.build_request_path,
        "criteria_weights": dict(checkpoint.criteria_weights),
        "search_policy": dict(checkpoint.search_policy),
        "calibration_selection_policy": dict(checkpoint.calibration_selection_policy),
        "functional_evaluation_selection_policy": (
            dict(checkpoint.functional_evaluation_selection_policy)
            if checkpoint.functional_evaluation_selection_policy is not None
            else None
        ),
        "flat_orchestration_policy": dict(checkpoint.flat_orchestration_policy),
        "recursion_policy": dict(checkpoint.recursion_policy),
        "policy_version": checkpoint.policy_version,
        "completed_nodes": [serialize_node_record(n) for n in checkpoint.completed_nodes],
        "pending_review_modules": [dict(m) for m in checkpoint.pending_review_modules],
        "total_nodes_created": checkpoint.total_nodes_created,
        "total_functional_evaluations_used": checkpoint.total_functional_evaluations_used,
        "total_calibration_runs_used": checkpoint.total_calibration_runs_used,
        "next_node_sequence": checkpoint.next_node_sequence,
        "warnings": list(checkpoint.warnings),
    }


def deserialize_checkpoint(data: dict[str, Any]) -> HierarchyCheckpoint:
    """The exact inverse of ``serialize_checkpoint``. Raises ``KeyError``/``TypeError``/
    ``ValueError`` for a malformed checkpoint -- never guesses a missing required field.
    Deliberately does **not** check ``checkpoint_version``/``policy_version`` compatibility --
    that is ``resume_hierarchical_recursive_modularization``'s own job (a clear, typed
    rejection, not a parse-time exception), so this function alone can always load whatever
    shape is on disk for inspection even when it turns out to be stale.
    """
    return HierarchyCheckpoint(
        checkpoint_version=data["checkpoint_version"],
        hierarchy_id=data["hierarchy_id"],
        root_model_id=data["root_model_id"],
        run_id_prefix=data["run_id_prefix"],
        correlation_id=data["correlation_id"],
        agent1_view_path=data["agent1_view_path"],
        stage_dir=data["stage_dir"],
        seed_modularization_id=data.get("seed_modularization_id"),
        exclude_single_module_from_ranking=bool(data["exclude_single_module_from_ranking"]),
        apply_resolution_correction=bool(data["apply_resolution_correction"]),
        build_request_path=data.get("build_request_path"),
        criteria_weights=dict(data["criteria_weights"]),
        search_policy=dict(data["search_policy"]),
        calibration_selection_policy=dict(data["calibration_selection_policy"]),
        functional_evaluation_selection_policy=(
            dict(data["functional_evaluation_selection_policy"])
            if data.get("functional_evaluation_selection_policy") is not None
            else None
        ),
        flat_orchestration_policy=dict(data["flat_orchestration_policy"]),
        recursion_policy=dict(data["recursion_policy"]),
        policy_version=data["policy_version"],
        completed_nodes=tuple(deserialize_node_record(n) for n in data.get("completed_nodes", ())),
        pending_review_modules=tuple(dict(m) for m in data.get("pending_review_modules", ())),
        total_nodes_created=data["total_nodes_created"],
        total_functional_evaluations_used=data["total_functional_evaluations_used"],
        total_calibration_runs_used=data["total_calibration_runs_used"],
        next_node_sequence=data["next_node_sequence"],
        warnings=tuple(data.get("warnings", ())),
    )


def flat_orchestration_policy_to_dict(policy: OrchestrationPolicy) -> dict[str, Any]:
    """``OrchestrationPolicy`` -> a plain dict -- the shape ``HierarchyCheckpoint
    .flat_orchestration_policy`` carries. A simple, flat dataclass of str/int/bool fields only;
    no nested structure to worry about."""
    return {
        "max_rounds": policy.max_rounds,
        "max_total_candidates": policy.max_total_candidates,
        "improvement_epsilon": policy.improvement_epsilon,
        "require_human_review": policy.require_human_review,
        "policy_version": policy.policy_version,
    }


def flat_orchestration_policy_from_dict(data: dict[str, Any]) -> OrchestrationPolicy:
    """The exact inverse of ``flat_orchestration_policy_to_dict``."""
    return OrchestrationPolicy(
        max_rounds=data["max_rounds"],
        max_total_candidates=data["max_total_candidates"],
        improvement_epsilon=data["improvement_epsilon"],
        require_human_review=data["require_human_review"],
        policy_version=data["policy_version"],
    )


def recursion_policy_to_dict(policy: HierarchicalRecursionPolicy) -> dict[str, Any]:
    """``HierarchicalRecursionPolicy`` -> a plain dict -- the shape ``HierarchyCheckpoint
    .recursion_policy`` carries."""
    return {
        "max_depth": policy.max_depth,
        "min_reactions_per_module": policy.min_reactions_per_module,
        "max_total_hierarchy_nodes": policy.max_total_hierarchy_nodes,
        "max_total_functional_evaluation_budget": policy.max_total_functional_evaluation_budget,
        "max_total_calibration_budget": policy.max_total_calibration_budget,
        "min_improvement_to_accept_child": policy.min_improvement_to_accept_child,
        "require_human_review": policy.require_human_review,
        "policy_version": policy.policy_version,
    }


def recursion_policy_from_dict(data: dict[str, Any]) -> HierarchicalRecursionPolicy:
    """The exact inverse of ``recursion_policy_to_dict``."""
    return HierarchicalRecursionPolicy(
        max_depth=data["max_depth"],
        min_reactions_per_module=data["min_reactions_per_module"],
        max_total_hierarchy_nodes=data["max_total_hierarchy_nodes"],
        max_total_functional_evaluation_budget=data["max_total_functional_evaluation_budget"],
        max_total_calibration_budget=data["max_total_calibration_budget"],
        min_improvement_to_accept_child=data["min_improvement_to_accept_child"],
        require_human_review=data["require_human_review"],
        policy_version=data["policy_version"],
    )


__all__ = [
    "deserialize_checkpoint",
    "deserialize_node_record",
    "flat_orchestration_policy_from_dict",
    "flat_orchestration_policy_to_dict",
    "recursion_policy_from_dict",
    "recursion_policy_to_dict",
    "serialize_checkpoint",
    "serialize_node_record",
]
