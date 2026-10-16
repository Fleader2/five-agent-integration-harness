"""Tests for the human-review/resume increment:
``app.harness.hierarchical_recursion.resume_hierarchical_recursive_modularization`` and
``HierarchyCheckpoint`` (de)serialization.

Mirrors ``tests/harness/test_hierarchical_recursion.py``'s own fake-injection convention
exactly: every test injects a fast, deterministic fake ``recursive_search_runner`` (never a
real call to ``run_recursive_candidate_search``). The one real, live subprocess exercise lives
in a standalone script run manually (see the completion report) rather than this fast suite.
"""

from __future__ import annotations

import json

import pytest

from app.harness.hierarchical_recursion import (
    HierarchicalRecursionCheckpointError,
    HierarchicalRecursionPolicy,
    HierarchyBranchStoppingReason,
    HumanReviewDecision,
    deserialize_checkpoint,
    resume_hierarchical_recursive_modularization,
    run_hierarchical_recursive_modularization,
    serialize_checkpoint,
)
from app.harness.recursive_candidate_search import (
    OrchestrationPolicy,
    RecursiveCandidateSearchResult,
    RoundRecord,
    StoppingReason,
)

# --- Fixtures ------------------------------------------------------------------------------------


def _candidate(candidate_id: str, module_ids: list[str], overall_score: str | None) -> dict:
    return {
        "candidate_id": candidate_id,
        "module_ids": module_ids,
        "module_count": len(module_ids),
        "overall_score": overall_score,
        "evaluated_weight_fraction": "1",
        "criterion_scores": [],
        "lineage": None,
    }


def _calibration_decision(candidate_id: str, module_id: str, content_key: list[list[str]]) -> dict:
    return {
        "candidate_id": candidate_id,
        "module_id": module_id,
        "content_key": content_key,
        "outcome": "CALIBRATE",
        "reason": "test fixture",
        "structural_score": "0.5",
        "rank": 1,
    }


def _round_summary(
    *,
    model_id: str,
    retained: list[dict] | None = None,
    degenerate: list[dict] | None = None,
    calibration_decisions: list[dict] | None = None,
) -> dict:
    return {
        "model_id": model_id,
        "retained": retained if retained is not None else [],
        "degenerate": degenerate if degenerate is not None else [],
        "calibration_decisions": calibration_decisions if calibration_decisions is not None else [],
        "calibration_requests": [],
        "locally_resolved_evidence": [],
        "functional_evaluation_decisions": [],
        "functional_evaluation_requests": [],
        "locally_resolved_functional_evidence": [],
    }


def _flat_orchestration_policy(**overrides) -> OrchestrationPolicy:
    merged = {
        "max_rounds": 1,
        "max_total_candidates": 1000,
        "improvement_epsilon": "0.01",
        "require_human_review": False,
        "policy_version": "test-v1",
    } | overrides
    return OrchestrationPolicy(**merged)


def _recursion_policy(**overrides) -> HierarchicalRecursionPolicy:
    merged = {
        "max_depth": 3,
        "min_reactions_per_module": 1,
        "max_total_hierarchy_nodes": 100,
        "max_total_functional_evaluation_budget": 100,
        "max_total_calibration_budget": 100,
        "min_improvement_to_accept_child": "0.1",
        "require_human_review": True,
        "policy_version": "test-v1",
    } | overrides
    return HierarchicalRecursionPolicy(**merged)


def _flat_result(
    round_summary: dict,
    *,
    stopping_reason: StoppingReason = StoppingReason.MAX_ROUNDS,
    calibration_runs_used: int = 1,
    functional_evaluations_used: int = 0,
) -> RecursiveCandidateSearchResult:
    return RecursiveCandidateSearchResult(
        orchestration_id="x",
        model_id=round_summary["model_id"],
        seed_modularization_id="seed",
        rounds=(
            RoundRecord(
                round_number=1,
                round_summary=round_summary,
                calibration_runs=(),
                best_overall_score=None,
            ),
        ),
        stopping_reason=stopping_reason,
        requires_user_review=False,
        total_candidates_seen=1,
        total_calibration_runs_used=calibration_runs_used,
        orchestration_policy=_flat_orchestration_policy(),
        policy_version="test-v1",
        total_functional_evaluations_used=functional_evaluations_used,
    )


def _never_provide_dataset(**kwargs):
    return None


def _run(recursive_search_runner, *, recursion_policy=None, tmp_path, **overrides):
    kwargs = {
        "agent1_view_path": tmp_path / "agent1_view.json",
        "criteria_weights": {"weights": [], "policy_version": "test-v1"},
        "search_policy": {
            "max_iterations": 1,
            "max_candidates_per_iteration": 10,
            "beam_width": 5,
            "allowed_operations": ["MOVE_REACTION"],
            "policy_version": "test-v1",
        },
        "calibration_selection_policy": {
            "max_candidates_per_generation": 10,
            "max_modules_per_candidate": None,
            "score_threshold": None,
            "rank_threshold": None,
            "only_if_could_change_ordering": False,
            "total_calibration_run_budget": 1000,
            "policy_version": "test-v1",
        },
        "flat_orchestration_policy": _flat_orchestration_policy(),
        "recursion_policy": recursion_policy or _recursion_policy(),
        "calibration_request_provider": _never_provide_dataset,
        "stage_dir": tmp_path,
        "correlation_id": "corr-1",
        "run_id_prefix": "test-run",
        "recursive_search_runner": recursive_search_runner,
    } | overrides
    return run_hierarchical_recursive_modularization(**kwargs)


def _root_two_eligible_runner(calls: list, *, modB_should_never_run: bool = False):
    """``root`` (modA/modB, each >= 1 reaction, score 0.5 vs degenerate baseline 0.1) ->
    pauses for review with both modA and modB pending. modA, if approved, is accepted (score
    0.8 vs baseline 0.3) with no further eligible children of its own (both its own children
    have 0 reactions in the gated fixture below, so never mind -- see ``min_reactions_per_module``
    per test). ``modB_should_never_run`` raises if the fake is ever asked to search modB
    (used by rejection tests, to prove a rejected module is truly never searched)."""

    def fake(**kwargs):
        calls.append(kwargs)
        submodel_module_id = kwargs.get("submodel_module_id")
        if submodel_module_id is None:
            summary = _round_summary(
                model_id="m1",
                retained=[_candidate("cand-root", ["modA", "modB"], "0.5")],
                degenerate=[_candidate("cand-root-degenerate", ["modAB"], "0.1")],
                calibration_decisions=[
                    _calibration_decision(
                        "cand-root", "modA", [["REACTION", "r1"], ["REACTION", "r1x"]]
                    ),
                    _calibration_decision(
                        "cand-root", "modB", [["REACTION", "r2"], ["REACTION", "r2x"]]
                    ),
                ],
            )
            return _flat_result(summary)
        if submodel_module_id == "modA":
            summary = _round_summary(
                model_id="m1::submodel::modA",
                retained=[_candidate("cand-childA", ["modA1", "modA2"], "0.8")],
                degenerate=[_candidate("cand-childA-degenerate", ["modA"], "0.3")],
                calibration_decisions=[
                    _calibration_decision("cand-childA", "modA1", [["REACTION", "r1a"]]),
                    _calibration_decision("cand-childA", "modA2", [["REACTION", "r1b"]]),
                ],
            )
            return _flat_result(summary)
        if submodel_module_id == "modB":
            if modB_should_never_run:
                raise AssertionError("modB was rejected and must never be searched")
            summary = _round_summary(
                model_id="m1::submodel::modB",
                retained=[_candidate("cand-childB", ["modB1", "modB2"], "0.9")],
                degenerate=[_candidate("cand-childB-degenerate", ["modB"], "0.2")],
                calibration_decisions=[
                    _calibration_decision("cand-childB", "modB1", [["REACTION", "r2a"]]),
                    _calibration_decision("cand-childB", "modB2", [["REACTION", "r2b"]]),
                ],
            )
            return _flat_result(summary)
        raise AssertionError(f"unexpected submodel_module_id {submodel_module_id!r}")

    return fake


def _pause(tmp_path, *, calls=None, recursion_policy=None):
    calls = calls if calls is not None else []
    result = _run(
        _root_two_eligible_runner(calls, modB_should_never_run=True),
        tmp_path=tmp_path,
        recursion_policy=recursion_policy,
    )
    assert result.requires_user_review is True
    assert result.checkpoint is not None
    pending_by_module = {m["module_id"]: m["pending_id"] for m in result.pending_review_modules}
    return result, calls, pending_by_module


# --- pause -> serialize -> deserialize -> approve -> resume successfully ------------------------


def test_pause_serialize_deserialize_approve_resume_succeeds(tmp_path):
    result, calls, pending_by_module = _pause(
        tmp_path, recursion_policy=_recursion_policy(min_reactions_per_module=2)
    )
    data = serialize_checkpoint(result.checkpoint)
    json_text = json.dumps(data)
    reloaded = deserialize_checkpoint(json.loads(json_text))
    assert reloaded == result.checkpoint

    resumed = resume_hierarchical_recursive_modularization(
        reloaded,
        {
            pending_by_module["modA"]: HumanReviewDecision.APPROVE,
            pending_by_module["modB"]: HumanReviewDecision.REJECT,
        },
        calibration_request_provider=_never_provide_dataset,
        recursive_search_runner=_root_two_eligible_runner(calls, modB_should_never_run=True),
    )
    assert len(calls) == 2  # root (before pause) + modA; modB never called
    modA_node = next(n for n in resumed.nodes if n.parent_module_id == "modA" and n.depth == 1)
    assert modA_node.accepted is True
    # min_reactions_per_module=2 means modA1/modA2 (1 reaction each) are both too small -- no
    # further pause from this branch.
    assert resumed.requires_user_review is False
    assert resumed.checkpoint is None


# --- pause -> reject one/all modules --------------------------------------------------------------


def test_reject_all_pending_modules_never_searches_any_of_them(tmp_path):
    calls = []
    result, calls, pending_by_module = _pause(tmp_path, calls=calls)

    def _fail_if_called(**kwargs):
        raise AssertionError("no module should ever be searched when every decision is REJECT")

    resumed = resume_hierarchical_recursive_modularization(
        result.checkpoint,
        {
            pending_by_module["modA"]: HumanReviewDecision.REJECT,
            pending_by_module["modB"]: HumanReviewDecision.REJECT,
        },
        calibration_request_provider=_never_provide_dataset,
        recursive_search_runner=_fail_if_called,
    )
    assert len(calls) == 1  # only the original root call; resume called the runner zero times
    assert resumed.requires_user_review is False
    assert resumed.checkpoint is None
    rejected = [n for n in resumed.nodes if n.depth == 1]
    assert len(rejected) == 2
    assert all(
        n.branch_stopping_reason is HierarchyBranchStoppingReason.HUMAN_REVIEW_REJECTED
        for n in rejected
    )
    assert all(n.accepted is False for n in rejected)


def test_reject_one_module_only_searches_the_approved_one(tmp_path):
    calls = []
    result, calls, pending_by_module = _pause(
        tmp_path, calls=calls, recursion_policy=_recursion_policy(min_reactions_per_module=2)
    )

    resumed = resume_hierarchical_recursive_modularization(
        result.checkpoint,
        {
            pending_by_module["modA"]: HumanReviewDecision.APPROVE,
            pending_by_module["modB"]: HumanReviewDecision.REJECT,
        },
        calibration_request_provider=_never_provide_dataset,
        recursive_search_runner=_root_two_eligible_runner(calls, modB_should_never_run=True),
    )
    assert len(calls) == 2
    modB_node = next(n for n in resumed.nodes if n.parent_module_id == "modB")
    assert modB_node.branch_stopping_reason is HierarchyBranchStoppingReason.HUMAN_REVIEW_REJECTED
    modA_node = next(n for n in resumed.nodes if n.parent_module_id == "modA" and n.depth == 1)
    assert modA_node.accepted is True


# --- mixed approve/reject decisions (also exercises a second-level pause) ------------------------


def test_mixed_decisions_and_second_level_pause(tmp_path):
    calls = []
    result, calls, pending_by_module = _pause(tmp_path, calls=calls)

    resumed = resume_hierarchical_recursive_modularization(
        result.checkpoint,
        {
            pending_by_module["modA"]: HumanReviewDecision.APPROVE,
            pending_by_module["modB"]: HumanReviewDecision.REJECT,
        },
        calibration_request_provider=_never_provide_dataset,
        recursive_search_runner=_root_two_eligible_runner(calls, modB_should_never_run=True),
    )
    assert len(calls) == 2
    # modA's own children (modA1/modA2) are each eligible (default min_reactions_per_module=1)
    # and require_human_review is still True -- a second-level pause is expected.
    assert resumed.requires_user_review is True
    assert resumed.checkpoint is not None
    pending_modules_again = {m["module_id"] for m in resumed.pending_review_modules}
    assert pending_modules_again == {"modA1", "modA2"}


# --- completed nodes are not rerun ----------------------------------------------------------------


def test_completed_nodes_are_carried_through_unchanged(tmp_path):
    calls = []
    result, calls, pending_by_module = _pause(
        tmp_path, calls=calls, recursion_policy=_recursion_policy(min_reactions_per_module=2)
    )
    root_node_before = next(n for n in result.nodes if n.depth == 0)

    resumed = resume_hierarchical_recursive_modularization(
        result.checkpoint,
        {
            pending_by_module["modA"]: HumanReviewDecision.APPROVE,
            pending_by_module["modB"]: HumanReviewDecision.REJECT,
        },
        calibration_request_provider=_never_provide_dataset,
        recursive_search_runner=_root_two_eligible_runner(calls, modB_should_never_run=True),
    )
    root_node_after = next(n for n in resumed.nodes if n.depth == 0)
    assert root_node_after == root_node_before
    # The root's own flat search ran exactly once -- resume never re-invoked it.
    root_calls = [c for c in calls if c.get("submodel_module_id") is None]
    assert len(root_calls) == 1


# --- budgets continue across resume ---------------------------------------------------------------


def test_global_calibration_budget_continues_across_resume(tmp_path):
    calls = []
    result, calls, pending_by_module = _pause(
        tmp_path, calls=calls, recursion_policy=_recursion_policy(min_reactions_per_module=2)
    )
    assert result.checkpoint.total_calibration_runs_used == 1  # root's own one flat search

    resumed = resume_hierarchical_recursive_modularization(
        result.checkpoint,
        {
            pending_by_module["modA"]: HumanReviewDecision.APPROVE,
            pending_by_module["modB"]: HumanReviewDecision.REJECT,
        },
        calibration_request_provider=_never_provide_dataset,
        recursive_search_runner=_root_two_eligible_runner(calls, modB_should_never_run=True),
    )
    # root (1) + modA (1) = 2 -- continuing from the checkpoint's own recorded value, never
    # reset to 0.
    assert resumed.total_calibration_runs_used == 2


# --- max-depth/node/budget stopping still works after resume -------------------------------------


def test_max_depth_stopping_applies_to_a_resumed_branch(tmp_path):
    calls = []
    result, calls, pending_by_module = _pause(
        tmp_path, calls=calls, recursion_policy=_recursion_policy(max_depth=1)
    )
    resumed = resume_hierarchical_recursive_modularization(
        result.checkpoint,
        {
            pending_by_module["modA"]: HumanReviewDecision.APPROVE,
            pending_by_module["modB"]: HumanReviewDecision.REJECT,
        },
        calibration_request_provider=_never_provide_dataset,
        recursive_search_runner=_root_two_eligible_runner(calls, modB_should_never_run=True),
    )
    modA_node = next(n for n in resumed.nodes if n.parent_module_id == "modA" and n.depth == 1)
    assert modA_node.accepted is True
    assert modA_node.branch_stopping_reason is HierarchyBranchStoppingReason.MAX_DEPTH
    assert resumed.requires_user_review is False


def test_max_total_hierarchy_nodes_stopping_applies_during_resume(tmp_path):
    calls = []
    # total_nodes_created after the root's own one search is 1 -- cap at exactly 1 more.
    result, calls, pending_by_module = _pause(
        tmp_path, calls=calls, recursion_policy=_recursion_policy(max_total_hierarchy_nodes=2)
    )
    resumed = resume_hierarchical_recursive_modularization(
        result.checkpoint,
        {
            pending_by_module["modA"]: HumanReviewDecision.APPROVE,
            pending_by_module["modB"]: HumanReviewDecision.APPROVE,
        },
        calibration_request_provider=_never_provide_dataset,
        recursive_search_runner=_root_two_eligible_runner(calls, modB_should_never_run=False),
    )
    assert resumed.total_nodes_created == 2
    exhausted = [
        n
        for n in resumed.nodes
        if n.branch_stopping_reason is HierarchyBranchStoppingReason.MAX_HIERARCHY_NODES_EXHAUSTED
    ]
    assert len(exhausted) == 1


def test_global_budget_exhaustion_stopping_applies_during_resume(tmp_path):
    calls = []
    result, calls, pending_by_module = _pause(
        tmp_path, calls=calls, recursion_policy=_recursion_policy(max_total_calibration_budget=1)
    )
    resumed = resume_hierarchical_recursive_modularization(
        result.checkpoint,
        {
            pending_by_module["modA"]: HumanReviewDecision.APPROVE,
            pending_by_module["modB"]: HumanReviewDecision.APPROVE,
        },
        calibration_request_provider=_never_provide_dataset,
        recursive_search_runner=_root_two_eligible_runner(calls, modB_should_never_run=False),
    )
    budget_exhausted = [
        n
        for n in resumed.nodes
        if n.branch_stopping_reason is HierarchyBranchStoppingReason.CALIBRATION_BUDGET_EXHAUSTED
    ]
    assert len(budget_exhausted) >= 1


# --- invalid/mismatched checkpoint rejection ------------------------------------------------------


def test_resume_rejects_wrong_checkpoint_version(tmp_path):
    result, _calls, pending_by_module = _pause(tmp_path)
    from dataclasses import replace

    bad_checkpoint = replace(result.checkpoint, checkpoint_version="some-other-version")
    with pytest.raises(HierarchicalRecursionCheckpointError):
        resume_hierarchical_recursive_modularization(
            bad_checkpoint,
            dict.fromkeys(pending_by_module.values(), HumanReviewDecision.REJECT),
            calibration_request_provider=_never_provide_dataset,
        )


def test_resume_rejects_wrong_policy_version(tmp_path):
    result, _calls, pending_by_module = _pause(tmp_path)
    from dataclasses import replace

    bad_checkpoint = replace(result.checkpoint, policy_version="some-stale-policy-version")
    with pytest.raises(HierarchicalRecursionCheckpointError):
        resume_hierarchical_recursive_modularization(
            bad_checkpoint,
            dict.fromkeys(pending_by_module.values(), HumanReviewDecision.REJECT),
            calibration_request_provider=_never_provide_dataset,
        )


def test_resume_rejects_missing_decision(tmp_path):
    result, _calls, pending_by_module = _pause(tmp_path)
    only_one = {pending_by_module["modA"]: HumanReviewDecision.REJECT}
    with pytest.raises(HierarchicalRecursionCheckpointError):
        resume_hierarchical_recursive_modularization(
            result.checkpoint,
            only_one,
            calibration_request_provider=_never_provide_dataset,
        )


def test_resume_rejects_unknown_pending_id(tmp_path):
    result, _calls, pending_by_module = _pause(tmp_path)
    decisions = dict.fromkeys(pending_by_module.values(), HumanReviewDecision.REJECT)
    decisions["not-a-real-pending-id"] = HumanReviewDecision.REJECT
    with pytest.raises(HierarchicalRecursionCheckpointError):
        resume_hierarchical_recursive_modularization(
            result.checkpoint,
            decisions,
            calibration_request_provider=_never_provide_dataset,
        )


def test_resume_rejects_invalid_decision_value(tmp_path):
    result, _calls, pending_by_module = _pause(tmp_path)
    decisions = dict.fromkeys(pending_by_module.values(), "MAYBE")
    with pytest.raises(HierarchicalRecursionCheckpointError):
        resume_hierarchical_recursive_modularization(
            result.checkpoint,
            decisions,
            calibration_request_provider=_never_provide_dataset,
        )


def test_resume_accepts_plain_string_decision_values(tmp_path):
    """Task instructions §3: decisions are keyed by stable identifiers with 'approve'/'reject'
    -- plain strings must work, not just the ``HumanReviewDecision`` enum."""
    calls = []
    result, calls, pending_by_module = _pause(tmp_path, calls=calls)
    resume_hierarchical_recursive_modularization(
        result.checkpoint,
        {
            pending_by_module["modA"]: "APPROVE",
            pending_by_module["modB"]: "REJECT",
        },
        calibration_request_provider=_never_provide_dataset,
        recursive_search_runner=_root_two_eligible_runner(calls, modB_should_never_run=True),
    )
    assert len(calls) == 2


# --- repeated/idempotent resume behavior ----------------------------------------------------------


def test_repeated_resume_with_identical_checkpoint_and_decisions_is_deterministic(tmp_path):
    result, _calls, pending_by_module = _pause(
        tmp_path, recursion_policy=_recursion_policy(min_reactions_per_module=2)
    )
    decisions = {
        pending_by_module["modA"]: HumanReviewDecision.APPROVE,
        pending_by_module["modB"]: HumanReviewDecision.REJECT,
    }

    calls1 = []
    resumed1 = resume_hierarchical_recursive_modularization(
        result.checkpoint,
        decisions,
        calibration_request_provider=_never_provide_dataset,
        recursive_search_runner=_root_two_eligible_runner(calls1, modB_should_never_run=True),
    )
    calls2 = []
    resumed2 = resume_hierarchical_recursive_modularization(
        result.checkpoint,
        decisions,
        calibration_request_provider=_never_provide_dataset,
        recursive_search_runner=_root_two_eligible_runner(calls2, modB_should_never_run=True),
    )
    assert resumed1.nodes == resumed2.nodes
    assert resumed1.total_nodes_created == resumed2.total_nodes_created
    assert resumed1.total_calibration_runs_used == resumed2.total_calibration_runs_used
    node_ids1 = [n.node_id for n in resumed1.nodes]
    node_ids2 = [n.node_id for n in resumed2.nodes]
    assert node_ids1 == node_ids2
    assert len(set(node_ids1)) == len(node_ids1)  # no duplicate node ids within one result


# --- hierarchy parent/child IDs remain reconstructable and consistent ----------------------------


def test_parent_child_ids_are_reconstructable_after_resume(tmp_path):
    calls = []
    result, calls, pending_by_module = _pause(tmp_path, calls=calls)
    root_node = next(n for n in result.nodes if n.depth == 0)

    # Every pending entry's own parent_node_id matches the paused node's own node_id.
    for pending in result.pending_review_modules:
        assert pending["parent_node_id"] == root_node.node_id

    resumed = resume_hierarchical_recursive_modularization(
        result.checkpoint,
        {
            pending_by_module["modA"]: HumanReviewDecision.APPROVE,
            pending_by_module["modB"]: HumanReviewDecision.REJECT,
        },
        calibration_request_provider=_never_provide_dataset,
        recursive_search_runner=_root_two_eligible_runner(calls, modB_should_never_run=True),
    )
    modA_node = next(n for n in resumed.nodes if n.parent_module_id == "modA" and n.depth == 1)
    assert modA_node.parent_modularization_id == root_node.child_modularization_id
    modB_node = next(n for n in resumed.nodes if n.parent_module_id == "modB")
    assert modB_node.parent_modularization_id == root_node.child_modularization_id
    # root_model_id is identical across every node, including ones added during resume.
    assert {n.root_model_id for n in resumed.nodes} == {root_node.root_model_id}
