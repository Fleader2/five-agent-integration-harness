"""Tests for the Automatic Functional-Evaluation Selection and Caching increment's own
harness-side half: ``app.harness.recursive_candidate_search.orchestration``'s new functional-
evaluation routing loop.

Mirrors ``tests/harness/test_recursive_candidate_search.py``'s own fixture/fake-injection
convention exactly -- every test here injects a fast, deterministic fake ``invoke_round``/
``functional_evaluation_runner`` (never a real subprocess call to Agent 2 or Agent 3). The real
subprocess wiring is covered by its own existing test suite; this file tests the recursive-loop
driver's own new functional-evaluation logic in isolation.
"""

from __future__ import annotations

from app.harness.module_functional_evaluation import ModuleFunctionalEvaluationWorkflowError
from app.harness.recursive_candidate_search import (
    FunctionalEvaluationRunOutcome,
    OrchestrationPolicy,
    StoppingReason,
    functional_evaluation_cache_key_for,
    run_recursive_candidate_search,
)

# --- Fixtures (mirrors test_recursive_candidate_search.py's own convention) --------------------


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


def _functional_decision(
    candidate_id: str,
    module_id: str,
    *,
    outcome: str = "EVALUATE",
    content_key: list[list[str]] | None = None,
) -> dict:
    return {
        "candidate_id": candidate_id,
        "module_id": module_id,
        "content_key": content_key or [["REACTION", module_id]],
        "outcome": outcome,
        "reason": "test fixture",
        "structural_score": "0.5",
        "rank": 1,
    }


def _functional_request_envelope(
    candidate_id: str,
    module_id: str,
    *,
    content_key: list[list[str]] | None = None,
    boundary_species_ids: list[str] | None = None,
    perturbation_targets: list[dict] | None = None,
) -> dict:
    return {
        "content_key": content_key or [["REACTION", module_id]],
        "request": {
            "request_id": f"freq::{module_id}",
            "correlation_id": "corr-1",
            "run_id": f"run::functional::{module_id}",
            "parent_model_id": "m1",
            "modularization_id": candidate_id,
            "module_id": module_id,
            "whole_network_handoff": {"antimony_text": "model m; end"},
            "baseline_request": {"request_id": f"baseline::{module_id}"},
            "perturbation_targets": perturbation_targets
            if perturbation_targets is not None
            else [
                {
                    "target_kind": "PARAMETER",
                    "target_id": "k1",
                    "fraction": "0.1",
                    "is_internal": True,
                }
            ],
            "internal_species_ids": ["a"],
            "boundary_species_ids": boundary_species_ids
            if boundary_species_ids is not None
            else ["a"],
            "requested_at": None,
        },
    }


def _functional_evaluation_result(
    module_id: str = "modA", agent3_report_id: str | None = "report-1"
) -> dict:
    return {
        "evaluation_id": f"functional-eval::{module_id}",
        "request_id": f"freq::{module_id}",
        "correlation_id": "corr-1",
        "run_id": f"run::functional::{module_id}",
        "parent_model_id": "m1",
        "modularization_id": "cand-1",
        "module_id": module_id,
        "status": "EVALUATED",
        "policy_version": "test-v1",
        "perturbation_effects": [],
        "warnings": [],
        "provenance_refs": (
            [f"agent3-report::{agent3_report_id}"] if agent3_report_id is not None else []
        ),
    }


def _round_summary(
    *,
    model_id: str = "m1",
    retained: list[dict] | None = None,
    degenerate: list[dict] | None = None,
    calibration_decisions: list[dict] | None = None,
    calibration_requests: list[dict] | None = None,
    locally_resolved_evidence: list[dict] | None = None,
    functional_evaluation_decisions: list[dict] | None = None,
    functional_evaluation_requests: list[dict] | None = None,
    locally_resolved_functional_evidence: list[dict] | None = None,
) -> dict:
    return {
        "search_id": "search::m1::seed",
        "model_id": model_id,
        "seed_candidate_id": "seed",
        "retained": retained if retained is not None else [],
        "degenerate": degenerate if degenerate is not None else [],
        "rejected_count": 0,
        "iterations_run": 1,
        "search_policy_version": "test-v1",
        "exclude_single_module_from_ranking": True,
        "search_warnings": [],
        "calibration_decisions": calibration_decisions if calibration_decisions is not None else [],
        "calibration_requests": calibration_requests if calibration_requests is not None else [],
        "locally_resolved_evidence": (
            locally_resolved_evidence if locally_resolved_evidence is not None else []
        ),
        "policy_version": "test-v1",
        "functional_evaluation_decisions": (
            functional_evaluation_decisions if functional_evaluation_decisions is not None else []
        ),
        "functional_evaluation_requests": (
            functional_evaluation_requests if functional_evaluation_requests is not None else []
        ),
        "locally_resolved_functional_evidence": (
            locally_resolved_functional_evidence
            if locally_resolved_functional_evidence is not None
            else []
        ),
    }


def _calibration_basic_policy(**overrides) -> dict:
    merged = {
        "max_candidates_per_generation": 10,
        "max_modules_per_candidate": None,
        "score_threshold": None,
        "rank_threshold": None,
        "only_if_could_change_ordering": False,
        "total_calibration_run_budget": 1000,
        "policy_version": "test-v1",
    } | overrides
    return merged


def _functional_basic_policy(**overrides) -> dict:
    merged = {
        "max_candidates_per_generation": 10,
        "max_modules_per_candidate": None,
        "score_threshold": None,
        "rank_threshold": None,
        "only_if_could_change_ordering": False,
        "total_functional_evaluation_budget": 1000,
        "policy_version": "test-v1",
    } | overrides
    return merged


def _orchestration_policy(**overrides) -> OrchestrationPolicy:
    merged = {
        "max_rounds": 5,
        "max_total_candidates": 1000,
        "improvement_epsilon": "0.01",
        "require_human_review": False,
        "policy_version": "test-v1",
    } | overrides
    return OrchestrationPolicy(**merged)


def _never_provide_dataset(**kwargs) -> None:
    return None


def _fake_calibration_runner(request, calibration_request, *, stage_dir, timeout_seconds=300.0):
    raise AssertionError("calibration_runner should never be called in these tests")


def _run(
    sequence: list[dict],
    *,
    orchestration_policy: OrchestrationPolicy | None = None,
    functional_evaluation_selection_policy: dict | None = None,
    functional_evaluation_runner=None,
    tmp_path,
):
    calls: list[dict] = []

    def fake_invoke_round(**kwargs):
        calls.append(kwargs)
        index = min(len(calls) - 1, len(sequence) - 1)
        return sequence[index]

    def fake_functional_evaluation_runner(request, *, stage_dir, timeout_seconds=300.0):
        return _functional_evaluation_result(module_id=request["module_id"])

    result = run_recursive_candidate_search(
        agent1_view_path=tmp_path / "agent1_view.json",
        criteria_weights={"weights": [], "policy_version": "test-v1"},
        search_policy={
            "max_iterations": 1,
            "max_candidates_per_iteration": 10,
            "beam_width": 5,
            "allowed_operations": ["MOVE_REACTION"],
            "policy_version": "test-v1",
        },
        calibration_selection_policy=_calibration_basic_policy(),
        orchestration_policy=orchestration_policy or _orchestration_policy(),
        calibration_request_provider=_never_provide_dataset,
        stage_dir=tmp_path,
        correlation_id="corr-1",
        run_id_prefix="test-run",
        invoke_round=fake_invoke_round,
        calibration_runner=_fake_calibration_runner,
        functional_evaluation_selection_policy=functional_evaluation_selection_policy,
        functional_evaluation_runner=(
            functional_evaluation_runner or fake_functional_evaluation_runner
        ),
    )
    return result, calls


# --- functional_evaluation_cache_key_for --------------------------------------------------------


def test_functional_evaluation_cache_key_for_is_deterministic():
    key1 = functional_evaluation_cache_key_for([["REACTION", "r1"]], ["a"], [])
    key2 = functional_evaluation_cache_key_for([["REACTION", "r1"]], ["a"], [])
    assert key1 == key2


def test_functional_evaluation_cache_key_for_sensitive_to_boundary_species():
    base = functional_evaluation_cache_key_for([["REACTION", "r1"]], ["a"], [])
    changed = functional_evaluation_cache_key_for([["REACTION", "r1"]], ["b"], [])
    assert base != changed


def test_functional_evaluation_cache_key_for_sensitive_to_perturbation_battery():
    base = functional_evaluation_cache_key_for(
        [["REACTION", "r1"]],
        ["a"],
        [{"target_kind": "PARAMETER", "target_id": "k1", "fraction": "0.1", "is_internal": True}],
    )
    changed = functional_evaluation_cache_key_for(
        [["REACTION", "r1"]],
        ["a"],
        [{"target_kind": "PARAMETER", "target_id": "k1", "fraction": "0.2", "is_internal": True}],
    )
    assert base != changed


# --- no policy -> no Agent 3 calls at all --------------------------------------------------------


def test_omitting_the_functional_policy_never_invokes_the_runner(tmp_path):
    round1 = _round_summary(
        retained=[_candidate("cand-1", ["modA", "modB"], "0.5")],
        functional_evaluation_decisions=[_functional_decision("cand-1", "modA")],
        functional_evaluation_requests=[_functional_request_envelope("cand-1", "modA")],
    )
    runner_calls = []

    def counting_runner(request, *, stage_dir, timeout_seconds=300.0):
        runner_calls.append(request)
        return _functional_evaluation_result(module_id=request["module_id"])

    result, _calls = _run(
        [round1],
        orchestration_policy=_orchestration_policy(max_rounds=1),
        functional_evaluation_selection_policy=None,
        functional_evaluation_runner=counting_runner,
        tmp_path=tmp_path,
    )
    assert runner_calls == []
    assert result.rounds[0].functional_evaluation_runs == ()
    assert result.total_functional_evaluations_used == 0


# --- identical evaluation reused from cache ------------------------------------------------------


def test_cached_functional_evidence_is_reused_across_rounds(tmp_path):
    decision = _functional_decision("cand-1", "modA")
    envelope = _functional_request_envelope("cand-1", "modA")
    round1 = _round_summary(
        retained=[_candidate("cand-1", ["modA", "modB"], "0.5")],
        functional_evaluation_decisions=[decision],
        functional_evaluation_requests=[envelope],
    )
    round2 = _round_summary(
        retained=[_candidate("cand-1", ["modA", "modB"], "0.5")],
        functional_evaluation_decisions=[decision],
        functional_evaluation_requests=[envelope],
    )
    runner_calls = []

    def counting_runner(request, *, stage_dir, timeout_seconds=300.0):
        runner_calls.append(request)
        return _functional_evaluation_result(module_id=request["module_id"])

    result, _calls = _run(
        [round1, round2],
        orchestration_policy=_orchestration_policy(max_rounds=2),
        functional_evaluation_selection_policy=_functional_basic_policy(),
        functional_evaluation_runner=counting_runner,
        tmp_path=tmp_path,
    )
    assert len(runner_calls) == 1  # only the first round actually ran Agent 3
    outcomes_round2 = [r.outcome for r in result.rounds[1].functional_evaluation_runs]
    assert outcomes_round2 == [FunctionalEvaluationRunOutcome.REUSED_CACHED_EVIDENCE]
    assert result.total_functional_evaluations_used == 1


# --- changed boundary/perturbation battery invalidates cache ------------------------------------


def test_changed_perturbation_battery_invalidates_functional_cache(tmp_path):
    decision = _functional_decision("cand-1", "modA")
    round1 = _round_summary(
        retained=[_candidate("cand-1", ["modA", "modB"], "0.5")],
        functional_evaluation_decisions=[decision],
        functional_evaluation_requests=[_functional_request_envelope("cand-1", "modA")],
    )
    changed_envelope = _functional_request_envelope(
        "cand-1",
        "modA",
        perturbation_targets=[
            {"target_kind": "PARAMETER", "target_id": "k2", "fraction": "0.1", "is_internal": True}
        ],
    )
    round2 = _round_summary(
        retained=[_candidate("cand-1", ["modA", "modB"], "0.5")],
        functional_evaluation_decisions=[decision],
        functional_evaluation_requests=[changed_envelope],
    )
    runner_calls = []

    def counting_runner(request, *, stage_dir, timeout_seconds=300.0):
        runner_calls.append(request)
        return _functional_evaluation_result(module_id=request["module_id"])

    _result, _calls = _run(
        [round1, round2],
        orchestration_policy=_orchestration_policy(max_rounds=2),
        functional_evaluation_selection_policy=_functional_basic_policy(),
        functional_evaluation_runner=counting_runner,
        tmp_path=tmp_path,
    )
    assert len(runner_calls) == 2  # the battery change means a genuinely different evaluation


def test_changed_boundary_species_invalidates_functional_cache(tmp_path):
    decision = _functional_decision("cand-1", "modA")
    round1 = _round_summary(
        retained=[_candidate("cand-1", ["modA", "modB"], "0.5")],
        functional_evaluation_decisions=[decision],
        functional_evaluation_requests=[_functional_request_envelope("cand-1", "modA")],
    )
    changed_envelope = _functional_request_envelope("cand-1", "modA", boundary_species_ids=["b"])
    round2 = _round_summary(
        retained=[_candidate("cand-1", ["modA", "modB"], "0.5")],
        functional_evaluation_decisions=[decision],
        functional_evaluation_requests=[changed_envelope],
    )
    runner_calls = []

    def counting_runner(request, *, stage_dir, timeout_seconds=300.0):
        runner_calls.append(request)
        return _functional_evaluation_result(module_id=request["module_id"])

    _result, _calls = _run(
        [round1, round2],
        orchestration_policy=_orchestration_policy(max_rounds=2),
        functional_evaluation_selection_policy=_functional_basic_policy(),
        functional_evaluation_runner=counting_runner,
        tmp_path=tmp_path,
    )
    assert len(runner_calls) == 2


# --- infrastructure failure is never cached ------------------------------------------------------


def test_functional_infrastructure_failure_is_never_cached_and_is_retried(tmp_path):
    decision = _functional_decision("cand-1", "modA")
    envelope = _functional_request_envelope("cand-1", "modA")
    round1 = _round_summary(
        retained=[_candidate("cand-1", ["modA", "modB"], "0.5")],
        functional_evaluation_decisions=[decision],
        functional_evaluation_requests=[envelope],
    )
    round2 = _round_summary(
        retained=[_candidate("cand-1", ["modA", "modB"], "0.5")],
        functional_evaluation_decisions=[decision],
        functional_evaluation_requests=[envelope],
    )
    call_count = {"n": 0}

    def flaky_runner(request, *, stage_dir, timeout_seconds=300.0):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise ModuleFunctionalEvaluationWorkflowError("simulated infrastructure failure")
        return _functional_evaluation_result(module_id=request["module_id"])

    result, _calls = _run(
        [round1, round2],
        orchestration_policy=_orchestration_policy(max_rounds=2),
        functional_evaluation_selection_policy=_functional_basic_policy(),
        functional_evaluation_runner=flaky_runner,
        tmp_path=tmp_path,
    )
    assert (
        result.rounds[0].functional_evaluation_runs[0].outcome
        is FunctionalEvaluationRunOutcome.INFRASTRUCTURE_FAILURE
    )
    assert (
        result.rounds[1].functional_evaluation_runs[0].outcome
        is FunctionalEvaluationRunOutcome.NEW_RUN_SUCCEEDED
    )
    assert call_count["n"] == 2  # the failed attempt was retried, never silently skipped
    assert result.total_functional_evaluations_used == 1


# --- locally-resolved evidence requires no round trip --------------------------------------------


def test_locally_resolved_functional_evidence_requires_no_round_trip(tmp_path):
    decision = _functional_decision("cand-1", "modA")
    round1 = _round_summary(
        retained=[_candidate("cand-1", ["modA", "modB"], "0.5")],
        functional_evaluation_decisions=[decision],
        locally_resolved_functional_evidence=[
            {
                "content_key": [["REACTION", "modA"]],
                "evaluation": _functional_evaluation_result(module_id="modA", agent3_report_id=None)
                | {"status": "INSUFFICIENT_TARGETS"},
            }
        ],
    )
    runner_calls = []

    def counting_runner(request, *, stage_dir, timeout_seconds=300.0):
        runner_calls.append(request)
        return _functional_evaluation_result(module_id=request["module_id"])

    result, _calls = _run(
        [round1],
        orchestration_policy=_orchestration_policy(max_rounds=1),
        functional_evaluation_selection_policy=_functional_basic_policy(),
        functional_evaluation_runner=counting_runner,
        tmp_path=tmp_path,
    )
    assert runner_calls == []
    assert (
        result.rounds[0].functional_evaluation_runs[0].outcome
        is FunctionalEvaluationRunOutcome.LOCALLY_RESOLVED
    )


# --- functional evaluation budget enforced --------------------------------------------------------


def test_stopping_reason_functional_evaluation_budget_exhausted(tmp_path):
    decision = _functional_decision("cand-1", "modA")
    round_summary = _round_summary(
        retained=[_candidate("cand-1", ["modA", "modB"], "0.5")],
        functional_evaluation_decisions=[decision],
        functional_evaluation_requests=[_functional_request_envelope("cand-1", "modA")],
    )
    result, calls = _run(
        [round_summary, round_summary],
        orchestration_policy=_orchestration_policy(max_rounds=5),
        functional_evaluation_selection_policy=_functional_basic_policy(
            total_functional_evaluation_budget=1
        ),
        tmp_path=tmp_path,
    )
    assert result.stopping_reason is StoppingReason.FUNCTIONAL_EVALUATION_BUDGET_EXHAUSTED
    assert len(calls) == 1
    assert result.total_functional_evaluations_used == 1


# --- functional + calibration evidence compose correctly ---------------------------------------


def test_functional_and_calibration_routing_are_independent(tmp_path):
    """Calibration's own budget is zero (so every CALIBRATE decision this round would be
    skipped by Agent 2's own gate before this harness ever sees one) -- the functional-
    evaluation routing loop must still run normally, confirming the two loops are genuinely
    independent (task instructions §5)."""
    functional_decision = _functional_decision("cand-1", "modA")
    round1 = _round_summary(
        retained=[_candidate("cand-1", ["modA", "modB"], "0.5")],
        calibration_decisions=[],  # Agent 2's own gate produced zero CALIBRATE decisions
        functional_evaluation_decisions=[functional_decision],
        functional_evaluation_requests=[_functional_request_envelope("cand-1", "modA")],
    )
    result, _calls = _run(
        [round1],
        orchestration_policy=_orchestration_policy(max_rounds=1),
        functional_evaluation_selection_policy=_functional_basic_policy(),
        tmp_path=tmp_path,
    )
    assert result.rounds[0].calibration_runs == ()
    assert len(result.rounds[0].functional_evaluation_runs) == 1
    assert (
        result.rounds[0].functional_evaluation_runs[0].outcome
        is FunctionalEvaluationRunOutcome.NEW_RUN_SUCCEEDED
    )


# --- deterministic repeated execution ------------------------------------------------------------


def test_deterministic_repeated_execution(tmp_path):
    decision = _functional_decision("cand-1", "modA")
    round1 = _round_summary(
        retained=[_candidate("cand-1", ["modA", "modB"], "0.5")],
        functional_evaluation_decisions=[decision],
        functional_evaluation_requests=[_functional_request_envelope("cand-1", "modA")],
    )
    result1, _ = _run(
        [round1],
        orchestration_policy=_orchestration_policy(max_rounds=1),
        functional_evaluation_selection_policy=_functional_basic_policy(),
        tmp_path=tmp_path / "a",
    )
    result2, _ = _run(
        [round1],
        orchestration_policy=_orchestration_policy(max_rounds=1),
        functional_evaluation_selection_policy=_functional_basic_policy(),
        tmp_path=tmp_path / "b",
    )
    outcomes1 = [r.outcome for r in result1.rounds[0].functional_evaluation_runs]
    outcomes2 = [r.outcome for r in result2.rounds[0].functional_evaluation_runs]
    assert outcomes1 == outcomes2


# --- recursive / materialized-submodel operation (threading only -- real behavior is Agent 2's
# own test suite's job) ------------------------------------------------------------------------


def test_functional_policy_is_threaded_to_every_round_call(tmp_path):
    round1 = _round_summary(retained=[_candidate("cand-1", ["modA", "modB"], "0.5")])
    round2 = _round_summary(retained=[_candidate("cand-1", ["modA", "modB"], "0.5")])
    policy = _functional_basic_policy()
    _result, calls = _run(
        [round1, round2],
        orchestration_policy=_orchestration_policy(max_rounds=2),
        functional_evaluation_selection_policy=policy,
        tmp_path=tmp_path,
    )
    assert len(calls) == 2
    for call in calls:
        assert call["functional_evaluation_selection_policy"] == policy
