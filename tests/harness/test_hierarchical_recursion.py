"""Tests for the Automatic Hierarchical Recursive Modularization increment:
``app.harness.hierarchical_recursion``.

Every test injects a fast, deterministic fake ``recursive_search_runner`` (never a real call to
``run_recursive_candidate_search``, let alone a real Agent 2/Agent 3/Agent 4 subprocess) --
mirrors ``tests/harness/test_recursive_candidate_search.py``'s own established fake-injection
convention, one level up: this package's own real behavior is to call
``run_recursive_candidate_search`` once per hierarchy node, and that function's own behavior is
already covered by its own, separate test suite.
"""

from __future__ import annotations

import copy

from app.harness.hierarchical_recursion import (
    HierarchicalRecursionPolicy,
    HierarchyBranchStoppingReason,
    run_hierarchical_recursive_modularization,
)
from app.harness.recursive_candidate_search import (
    OrchestrationPolicy,
    RecursiveCandidateSearchResult,
    RoundRecord,
    StoppingReason,
)

# --- Fixtures -----------------------------------------------------------------------------------


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
        "min_reactions_per_module": 2,
        "max_total_hierarchy_nodes": 100,
        "max_total_functional_evaluation_budget": 100,
        "max_total_calibration_budget": 100,
        "min_improvement_to_accept_child": "0.1",
        "require_human_review": False,
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


def _two_level_runner(calls: list):
    """``root`` (modA/modB, each 2 reactions) -> modA accepted (score improves over its own
    degenerate baseline), modB rejected (no valid child decomposition)."""

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
                        "cand-root", "modA", [["REACTION", "r1"], ["REACTION", "r2"]]
                    ),
                    _calibration_decision(
                        "cand-root", "modB", [["REACTION", "r3"], ["REACTION", "r4"]]
                    ),
                ],
            )
        elif submodel_module_id == "modA":
            summary = _round_summary(
                model_id="m1::submodel::modA",
                retained=[_candidate("cand-childA", ["modA1", "modA2"], "0.8")],
                degenerate=[_candidate("cand-childA-degenerate", ["modA"], "0.3")],
                calibration_decisions=[
                    _calibration_decision("cand-childA", "modA1", [["REACTION", "r1"]]),
                    _calibration_decision("cand-childA", "modA2", [["REACTION", "r2"]]),
                ],
            )
        elif submodel_module_id == "modB":
            summary = _round_summary(
                model_id="m1::submodel::modB",
                retained=[],
                degenerate=[_candidate("cand-childB-degenerate", ["modB"], "0.2")],
            )
        else:
            raise AssertionError(f"unexpected submodel_module_id {submodel_module_id!r}")
        return _flat_result(summary)

    return fake


# --- successful two-level hierarchy / selective descent ------------------------------------------


def test_successful_two_level_hierarchy_descends_only_into_eligible_modules(tmp_path):
    calls: list = []
    result = _run(_two_level_runner(calls), tmp_path=tmp_path)

    assert len(calls) == 3  # root, modA, modB
    assert result.total_nodes_created == 3
    by_depth = {n.depth: [] for n in result.nodes}
    for n in result.nodes:
        by_depth[n.depth].append(n)
    assert len(by_depth[0]) == 1
    assert by_depth[0][0].accepted is True
    assert by_depth[0][0].child_modularization_id == "cand-root"

    depth1_by_module = {n.parent_module_id: n for n in by_depth[1]}
    assert depth1_by_module["modA"].accepted is True
    assert depth1_by_module["modA"].child_modularization_id == "cand-childA"
    # modA1/modA2 each have only 1 reaction (< min_reactions_per_module=2) -- no third level.
    assert depth1_by_module["modA"].branch_stopping_reason is (
        HierarchyBranchStoppingReason.NO_ELIGIBLE_MODULES
    )
    assert depth1_by_module["modB"].accepted is False
    assert depth1_by_module["modB"].branch_stopping_reason is (
        HierarchyBranchStoppingReason.NO_VALID_CHILD_DECOMPOSITION
    )

    # modA1/modA2 each get their own cheap, never-run disclosure node -- MODULE_TOO_SMALL,
    # never silently skipped -- without consuming a hierarchy-node budget slot (only 3 real
    # searches ever ran: len(calls) == 3 above).
    depth2_by_module = {n.parent_module_id: n for n in by_depth.get(2, [])}
    assert set(depth2_by_module) == {"modA1", "modA2"}
    assert all(
        n.branch_stopping_reason is HierarchyBranchStoppingReason.MODULE_TOO_SMALL
        and n.accepted is False
        for n in depth2_by_module.values()
    )


# --- depth limit ---------------------------------------------------------------------------------


def test_depth_limit_stops_descent():
    """A module that would otherwise keep being eligible stops exactly at max_depth."""

    def fake(**kwargs):
        submodel_module_id = kwargs.get("submodel_module_id")
        module_id = "mod" if submodel_module_id is None else submodel_module_id
        summary = _round_summary(
            model_id=f"m1::{module_id}",
            retained=[_candidate(f"cand-{module_id}", [f"{module_id}X", f"{module_id}Y"], "0.9")],
            degenerate=[_candidate(f"cand-{module_id}-degenerate", [module_id], "0.1")],
            calibration_decisions=[
                _calibration_decision(
                    f"cand-{module_id}",
                    f"{module_id}X",
                    [["REACTION", f"{module_id}-r1"], ["REACTION", f"{module_id}-r2"]],
                ),
                _calibration_decision(
                    f"cand-{module_id}",
                    f"{module_id}Y",
                    [["REACTION", f"{module_id}-r3"], ["REACTION", f"{module_id}-r4"]],
                ),
            ],
        )
        return _flat_result(summary)

    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        from pathlib import Path

        result = _run(fake, recursion_policy=_recursion_policy(max_depth=2), tmp_path=Path(tmp))
    depths = sorted({n.depth for n in result.nodes})
    assert max(depths) == 2
    leaf_nodes = [n for n in result.nodes if n.depth == 2]
    assert leaf_nodes
    assert all(
        n.branch_stopping_reason is HierarchyBranchStoppingReason.MAX_DEPTH for n in leaf_nodes
    )


# --- global budget enforcement ------------------------------------------------------------------


def test_global_calibration_budget_enforced_across_levels(tmp_path):
    calls: list = []

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
                        "cand-root", "modA", [["REACTION", "r1"], ["REACTION", "r2"]]
                    ),
                    _calibration_decision(
                        "cand-root", "modB", [["REACTION", "r3"], ["REACTION", "r4"]]
                    ),
                ],
            )
            return _flat_result(summary, calibration_runs_used=2)
        summary = _round_summary(
            model_id=f"m1::submodel::{submodel_module_id}",
            retained=[],
            degenerate=[],
        )
        return _flat_result(summary, calibration_runs_used=0)

    result = _run(
        fake,
        recursion_policy=_recursion_policy(max_total_calibration_budget=2),
        tmp_path=tmp_path,
    )
    # root consumes the entire global calibration budget (2) -- both depth-1 children must be
    # skipped with CALIBRATION_BUDGET_EXHAUSTED, never even calling the runner for them.
    assert len(calls) == 1
    budget_exhausted_nodes = [
        n
        for n in result.nodes
        if n.branch_stopping_reason is HierarchyBranchStoppingReason.CALIBRATION_BUDGET_EXHAUSTED
    ]
    assert len(budget_exhausted_nodes) == 2
    assert result.total_calibration_runs_used == 2


# --- cache reuse across hierarchy levels --------------------------------------------------------


def test_shared_cache_instances_are_passed_to_every_level(tmp_path):
    calls: list = []
    _run(_two_level_runner(calls), tmp_path=tmp_path)
    assert len(calls) == 3
    caches = {id(c["cache"]) for c in calls}
    functional_caches = {id(c["functional_cache"]) for c in calls}
    assert len(caches) == 1  # the identical cache instance, every level
    assert len(functional_caches) == 1


def test_every_child_level_forces_exclude_single_module_from_ranking(tmp_path):
    """A child node's own acceptance rule depends on the degenerate baseline actually being
    computed -- regression test for a real bug caught by a live subprocess smoke test, where
    passing the root-level ``exclude_single_module_from_ranking=False`` straight through to
    every child level silently disabled that baseline (there is no 'leave the parent module
    intact' comparison possible if degenerate candidates are never tracked at all)."""
    calls: list = []
    _run(
        _two_level_runner(calls),
        tmp_path=tmp_path,
        exclude_single_module_from_ranking=False,
    )
    assert len(calls) == 3
    root_call, *child_calls = calls
    assert root_call["exclude_single_module_from_ranking"] is False
    assert all(c["exclude_single_module_from_ranking"] is True for c in child_calls)


# --- poor child decomposition rejected / no-improvement stopping --------------------------------


def test_poor_child_decomposition_is_rejected_for_insufficient_improvement(tmp_path):
    def fake(**kwargs):
        submodel_module_id = kwargs.get("submodel_module_id")
        if submodel_module_id is None:
            summary = _round_summary(
                model_id="m1",
                retained=[_candidate("cand-root", ["modA", "modB"], "0.5")],
                degenerate=[_candidate("cand-root-degenerate", ["modAB"], "0.1")],
                calibration_decisions=[
                    _calibration_decision(
                        "cand-root", "modA", [["REACTION", "r1"], ["REACTION", "r2"]]
                    ),
                    _calibration_decision(
                        "cand-root", "modB", [["REACTION", "r3"], ["REACTION", "r4"]]
                    ),
                ],
            )
            return _flat_result(summary)
        # the child's own best candidate barely beats its own degenerate baseline -- well
        # below min_improvement_to_accept_child=0.1.
        summary = _round_summary(
            model_id=f"m1::submodel::{submodel_module_id}",
            retained=[_candidate("cand-child", ["x", "y"], "0.31")],
            degenerate=[_candidate("cand-child-degenerate", ["whole"], "0.30")],
            calibration_decisions=[
                _calibration_decision("cand-child", "x", [["REACTION", "rx"]]),
                _calibration_decision("cand-child", "y", [["REACTION", "ry"]]),
            ],
        )
        return _flat_result(summary)

    result = _run(fake, tmp_path=tmp_path)
    depth1_nodes = [n for n in result.nodes if n.depth == 1]
    assert depth1_nodes
    assert all(n.accepted is False for n in depth1_nodes)
    assert all(
        n.branch_stopping_reason is HierarchyBranchStoppingReason.INSUFFICIENT_IMPROVEMENT
        for n in depth1_nodes
    )


# --- human-review pause --------------------------------------------------------------------------


def test_human_review_pauses_before_descending(tmp_path):
    calls: list = []
    result = _run(
        _two_level_runner(calls),
        recursion_policy=_recursion_policy(require_human_review=True),
        tmp_path=tmp_path,
    )
    assert len(calls) == 1  # only the root ran -- never descended into modA/modB
    assert result.requires_user_review is True
    assert len(result.pending_review_modules) == 2
    pending_by_module = {m["module_id"]: m for m in result.pending_review_modules}
    assert pending_by_module["modA"]["reaction_count"] == 2
    assert pending_by_module["modB"]["reaction_count"] == 2
    assert pending_by_module["modA"]["parent_modularization_id"] == "cand-root"
    root_node = result.nodes[0]
    assert root_node.branch_stopping_reason is HierarchyBranchStoppingReason.HUMAN_REVIEW_GATE


# --- deterministic repeated execution ------------------------------------------------------------


def test_deterministic_repeated_execution(tmp_path):
    calls1: list = []
    result1 = _run(_two_level_runner(calls1), tmp_path=tmp_path / "a")
    calls2: list = []
    result2 = _run(_two_level_runner(calls2), tmp_path=tmp_path / "b")
    assert [(n.depth, n.accepted, n.branch_stopping_reason) for n in result1.nodes] == [
        (n.depth, n.accepted, n.branch_stopping_reason) for n in result2.nodes
    ]
    assert result1.total_nodes_created == result2.total_nodes_created


# --- complete parent/child lineage --------------------------------------------------------------


def test_complete_parent_child_lineage_is_reconstructable(tmp_path):
    calls: list = []
    result = _run(_two_level_runner(calls), tmp_path=tmp_path)
    root = next(n for n in result.nodes if n.depth == 0)
    child_a = next(n for n in result.nodes if n.depth == 1 and n.parent_module_id == "modA")
    assert root.parent_modularization_id is None
    assert root.parent_module_id is None
    assert root.root_model_id == child_a.root_model_id  # every node shares the one root id
    assert child_a.parent_modularization_id == root.child_modularization_id
    assert child_a.parent_module_id == "modA"
    assert child_a.child_submodel_id == "m1::submodel::modA"
    assert child_a.child_modularization_id == "cand-childA"
    assert child_a.child_module_ids == ("modA1", "modA2")
    assert child_a.criteria_weights == root.criteria_weights
    assert child_a.recursive_search_policy_version


# --- GENERATED/IMPORTED symmetry ------------------------------------------------------------------


def test_driver_behavior_is_identical_regardless_of_model_origin_labeling(tmp_path):
    """The driver never inspects model-origin-specific fields -- it only ever reads the
    generic ``round_summary``/``RecursiveCandidateSearchResult`` shape, so a GENERATED-origin
    and an IMPORTED-origin model's own identically-shaped round summaries must produce
    identical hierarchy decisions."""

    def make_runner(model_id_prefix: str):
        def fake(**kwargs):
            submodel_module_id = kwargs.get("submodel_module_id")
            if submodel_module_id is None:
                summary = _round_summary(
                    model_id=model_id_prefix,
                    retained=[_candidate("cand-root", ["modA"], "0.5")],
                    degenerate=[_candidate("cand-root-degenerate", ["modA-whole"], "0.1")],
                    calibration_decisions=[
                        _calibration_decision(
                            "cand-root", "modA", [["REACTION", "r1"], ["REACTION", "r2"]]
                        ),
                    ],
                )
            else:
                summary = _round_summary(
                    model_id=f"{model_id_prefix}::submodel::modA", retained=[], degenerate=[]
                )
            return _flat_result(summary)

        return fake

    result_generated = _run(make_runner("generated-model"), tmp_path=tmp_path / "g")
    result_imported = _run(make_runner("imported-model"), tmp_path=tmp_path / "i")
    shapes_g = [(n.depth, n.accepted, n.branch_stopping_reason) for n in result_generated.nodes]
    shapes_i = [(n.depth, n.accepted, n.branch_stopping_reason) for n in result_imported.nodes]
    assert shapes_g == shapes_i


# --- no canonical parent-model mutation ----------------------------------------------------------


def test_never_mutates_caller_supplied_dicts(tmp_path):
    calls: list = []
    criteria_weights = {
        "weights": [{"criterion": "TOPOLOGICAL_SEPARATION", "weight": "1"}],
        "policy_version": "v1",
    }
    calibration_policy = {
        "max_candidates_per_generation": 10,
        "max_modules_per_candidate": None,
        "score_threshold": None,
        "rank_threshold": None,
        "only_if_could_change_ordering": False,
        "total_calibration_run_budget": 1000,
        "policy_version": "test-v1",
    }
    before_weights = copy.deepcopy(criteria_weights)
    before_calibration = copy.deepcopy(calibration_policy)
    _run(
        _two_level_runner(calls),
        tmp_path=tmp_path,
        criteria_weights=criteria_weights,
        calibration_selection_policy=calibration_policy,
    )
    assert criteria_weights == before_weights
    assert calibration_policy == before_calibration
