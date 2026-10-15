"""Tests for the Recursive Agent-4-Assisted Candidate Search Orchestration increment's own
harness-side half: ``app.harness.recursive_candidate_search``.

Every test here injects a fast, deterministic fake ``invoke_round``/``calibration_runner``
(never a real subprocess call to either Agent 2 or Agent 3/Agent 4) -- consistent with this
project's own established split (``tests/harness/test_module_calibration_workflow.py``'s own
"unit tests... fast, deterministic" vs. "one real, full round trip" convention). The real
subprocess wiring (``agent2_round.invoke_agent2_candidate_search_round``,
``app.harness.module_calibration.run_module_calibration_workflow``) is each already covered by
its own existing test suite; this file tests the recursive-loop driver's own logic in
isolation.
"""

from __future__ import annotations

from decimal import Decimal

from app.harness.module_calibration import ModuleCalibrationWorkflowError
from app.harness.recursive_candidate_search import (
    CalibrationRunOutcome,
    FileCalibrationEvidenceCache,
    OrchestrationPolicy,
    StoppingReason,
    cache_key_for,
    run_recursive_candidate_search,
)

# --- Fixtures ---------------------------------------------------------------------------------


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


def _decision(
    candidate_id: str,
    module_id: str,
    *,
    outcome: str = "CALIBRATE",
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


def _request_envelope(
    candidate_id: str,
    module_id: str,
    *,
    content_key: list[list[str]] | None = None,
    boundary_ports: list[dict] | None = None,
    dataset_refs: list[dict] | None = None,
) -> dict:
    return {
        "content_key": content_key or [["REACTION", module_id]],
        "request": {
            "request_id": f"req::{module_id}",
            "correlation_id": "corr-1",
            "run_id": f"run::{module_id}",
            "parent_model_id": "m1",
            "modularization_id": candidate_id,
            "module_id": module_id,
            "module_handoff": {"antimony_text": "model m; end"},
            "boundary_ports": boundary_ports
            if boundary_ports is not None
            else [
                {
                    "port_id": f"port-{module_id}",
                    "species_id": "a",
                    "direction": "INPUT",
                    "externally_controlled": True,
                    "initial_value": "1",
                    "unit": None,
                }
            ],
            "calibration_dataset_references": dataset_refs or [],
            "requested_at": None,
        },
    }


def _round_summary(
    *,
    model_id: str = "m1",
    retained: list[dict] | None = None,
    degenerate: list[dict] | None = None,
    calibration_decisions: list[dict] | None = None,
    calibration_requests: list[dict] | None = None,
    locally_resolved_evidence: list[dict] | None = None,
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
    }


def _evaluation(
    status: str = "CALIBRATION_SUPPORTED",
    module_id: str = "modA",
    agent4_run_id: str | None = "run-1",
) -> dict:
    return {
        "evaluation_id": f"eval::{module_id}",
        "request_id": f"req::{module_id}",
        "correlation_id": "corr-1",
        "run_id": f"run::{module_id}",
        "parent_model_id": "m1",
        "modularization_id": "cand-1",
        "module_id": module_id,
        "status": status,
        "policy_version": "test-v1",
        "fit_quality": None,
        "identifiability_findings": [],
        "parameter_uncertainty": [],
        "parameter_correlations": [],
        "boundary_sensitivity_findings": [],
        "parameters_requiring_external_context": [],
        "parameter_stability": [],
        "warnings": [],
        "provenance_refs": (
            [f"agent4-report::{agent4_run_id}"] if agent4_run_id is not None else []
        ),
    }


def _calibration_request_dict() -> dict:
    return {"request_id": "calib-req-1", "targets": [], "observations": {}}


def _basic_policy(**overrides) -> dict:
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


def _orchestration_policy(**overrides) -> OrchestrationPolicy:
    merged = {
        "max_rounds": 5,
        "max_total_candidates": 1000,
        "improvement_epsilon": "0.01",
        "require_human_review": False,
        "policy_version": "test-v1",
    } | overrides
    return OrchestrationPolicy(**merged)


def _always_provide_dataset(**kwargs) -> dict:
    return _calibration_request_dict()


def _never_provide_dataset(**kwargs) -> None:
    return None


def _run(
    sequence: list[dict],
    *,
    orchestration_policy: OrchestrationPolicy | None = None,
    calibration_selection_policy: dict | None = None,
    calibration_runner=None,
    calibration_request_provider=_always_provide_dataset,
    tmp_path,
    submodel_module_id: str | None = None,
):
    calls: list[dict] = []

    def fake_invoke_round(**kwargs):
        calls.append(kwargs)
        index = min(len(calls) - 1, len(sequence) - 1)
        return sequence[index]

    def fake_calibration_runner(request, calibration_request, *, stage_dir, timeout_seconds=300.0):
        return _evaluation(module_id=request["module_id"])

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
        calibration_selection_policy=calibration_selection_policy or _basic_policy(),
        orchestration_policy=orchestration_policy or _orchestration_policy(),
        calibration_request_provider=calibration_request_provider,
        stage_dir=tmp_path,
        correlation_id="corr-1",
        run_id_prefix="test-run",
        submodel_module_id=submodel_module_id,
        invoke_round=fake_invoke_round,
        calibration_runner=calibration_runner or fake_calibration_runner,
    )
    return result, calls


# --- cache_key_for --------------------------------------------------------------------------


def test_cache_key_for_is_deterministic():
    key1 = cache_key_for([["REACTION", "r1"]], [], [])
    key2 = cache_key_for([["REACTION", "r1"]], [], [])
    assert key1 == key2


def test_cache_key_for_sensitive_to_boundary_treatment():
    base = cache_key_for(
        [["REACTION", "r1"]],
        [{"species_id": "a", "direction": "INPUT", "externally_controlled": True}],
        [],
    )
    changed = cache_key_for(
        [["REACTION", "r1"]],
        [{"species_id": "a", "direction": "OUTPUT", "externally_controlled": True}],
        [],
    )
    assert base != changed


def test_cache_key_for_sensitive_to_dataset_references():
    base = cache_key_for([["REACTION", "r1"]], [], [{"dataset_id": "d1"}])
    changed = cache_key_for([["REACTION", "r1"]], [], [{"dataset_id": "d2"}])
    assert base != changed


def test_file_cache_stores_and_reuses(tmp_path):
    cache = FileCalibrationEvidenceCache(tmp_path / "cache")
    assert cache.get("k1") is None
    cache.put("k1", {"status": "CALIBRATION_SUPPORTED"})
    assert cache.get("k1") == {"status": "CALIBRATION_SUPPORTED"}


# --- Caching within the orchestration loop ----------------------------------------------------


def test_cached_module_evidence_is_reused_across_rounds(tmp_path):
    decision = _decision("cand-1", "modA")
    envelope = _request_envelope("cand-1", "modA")
    round1 = _round_summary(
        retained=[_candidate("cand-1", ["modA", "modB"], "0.5")],
        calibration_decisions=[decision],
        calibration_requests=[envelope],
    )
    # Round 2: the identical module (same content key/boundary/dataset) is selected again --
    # it must be *reused*, never recalibrated.
    round2 = _round_summary(
        retained=[_candidate("cand-1", ["modA", "modB"], "0.5")],
        calibration_decisions=[decision],
        calibration_requests=[envelope],
    )
    runner_calls = []

    def counting_runner(request, calibration_request, *, stage_dir, timeout_seconds=300.0):
        runner_calls.append(request)
        return _evaluation(module_id=request["module_id"])

    result, _calls = _run(
        [round1, round2],
        orchestration_policy=_orchestration_policy(max_rounds=2),
        calibration_runner=counting_runner,
        tmp_path=tmp_path,
    )
    assert len(runner_calls) == 1  # only the first round actually ran Agent 3/Agent 4
    outcomes_round2 = [r.outcome for r in result.rounds[1].calibration_runs]
    assert outcomes_round2 == [CalibrationRunOutcome.REUSED_CACHED_EVIDENCE]


def test_changed_boundary_treatment_invalidates_cache(tmp_path):
    decision = _decision("cand-1", "modA")
    round1 = _round_summary(
        retained=[_candidate("cand-1", ["modA", "modB"], "0.5")],
        calibration_decisions=[decision],
        calibration_requests=[_request_envelope("cand-1", "modA")],
    )
    changed_envelope = _request_envelope(
        "cand-1",
        "modA",
        boundary_ports=[
            {
                "port_id": "port-modA",
                "species_id": "a",
                "direction": "OUTPUT",  # changed from INPUT
                "externally_controlled": True,
                "initial_value": "1",
                "unit": None,
            }
        ],
    )
    round2 = _round_summary(
        retained=[_candidate("cand-1", ["modA", "modB"], "0.5")],
        calibration_decisions=[decision],
        calibration_requests=[changed_envelope],
    )
    runner_calls = []

    def counting_runner(request, calibration_request, *, stage_dir, timeout_seconds=300.0):
        runner_calls.append(request)
        return _evaluation(module_id=request["module_id"])

    _result, _calls = _run(
        [round1, round2],
        orchestration_policy=_orchestration_policy(max_rounds=2),
        calibration_runner=counting_runner,
        tmp_path=tmp_path,
    )
    assert len(runner_calls) == 2  # the boundary change means a genuinely different module


def test_infrastructure_failure_is_never_cached_and_is_retried(tmp_path):
    decision = _decision("cand-1", "modA")
    envelope = _request_envelope("cand-1", "modA")
    round1 = _round_summary(
        retained=[_candidate("cand-1", ["modA", "modB"], "0.5")],
        calibration_decisions=[decision],
        calibration_requests=[envelope],
    )
    round2 = _round_summary(
        retained=[_candidate("cand-1", ["modA", "modB"], "0.5")],
        calibration_decisions=[decision],
        calibration_requests=[envelope],
    )
    call_count = {"n": 0}

    def flaky_runner(request, calibration_request, *, stage_dir, timeout_seconds=300.0):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise ModuleCalibrationWorkflowError("simulated infrastructure failure")
        return _evaluation(module_id=request["module_id"])

    result, _calls = _run(
        [round1, round2],
        orchestration_policy=_orchestration_policy(max_rounds=2),
        calibration_runner=flaky_runner,
        tmp_path=tmp_path,
    )
    assert (
        result.rounds[0].calibration_runs[0].outcome == CalibrationRunOutcome.INFRASTRUCTURE_FAILURE
    )
    assert result.rounds[1].calibration_runs[0].outcome == CalibrationRunOutcome.NEW_RUN_SUCCEEDED
    assert call_count["n"] == 2  # the failed attempt was retried, never silently skipped


def test_no_dataset_available_skips_without_calling_the_runner(tmp_path):
    decision = _decision("cand-1", "modA")
    envelope = _request_envelope("cand-1", "modA")
    round1 = _round_summary(
        retained=[_candidate("cand-1", ["modA", "modB"], "0.5")],
        calibration_decisions=[decision],
        calibration_requests=[envelope],
    )
    runner_calls = []

    def counting_runner(request, calibration_request, *, stage_dir, timeout_seconds=300.0):
        runner_calls.append(request)
        return _evaluation(module_id=request["module_id"])

    result, _calls = _run(
        [round1],
        orchestration_policy=_orchestration_policy(max_rounds=1),
        calibration_runner=counting_runner,
        calibration_request_provider=_never_provide_dataset,
        tmp_path=tmp_path,
    )
    assert runner_calls == []
    assert (
        result.rounds[0].calibration_runs[0].outcome == CalibrationRunOutcome.NO_DATASET_AVAILABLE
    )


def test_locally_resolved_evidence_requires_no_round_trip(tmp_path):
    decision = _decision("cand-1", "modA")
    round1 = _round_summary(
        retained=[_candidate("cand-1", ["modA", "modB"], "0.5")],
        calibration_decisions=[decision],
        locally_resolved_evidence=[
            {
                "content_key": [["REACTION", "modA"]],
                "evaluation": _evaluation(
                    status="BOUNDARY_INADEQUATE", module_id="modA", agent4_run_id=None
                ),
            }
        ],
    )
    runner_calls = []

    def counting_runner(request, calibration_request, *, stage_dir, timeout_seconds=300.0):
        runner_calls.append(request)
        return _evaluation(module_id=request["module_id"])

    result, _calls = _run(
        [round1],
        orchestration_policy=_orchestration_policy(max_rounds=1),
        calibration_runner=counting_runner,
        tmp_path=tmp_path,
    )
    assert runner_calls == []
    assert result.rounds[0].calibration_runs[0].outcome == CalibrationRunOutcome.LOCALLY_RESOLVED


# --- Stopping rules -----------------------------------------------------------------------------


def test_stopping_reason_max_rounds(tmp_path):
    # A genuinely different structural partition and a genuinely improving score each round --
    # avoids triggering any convergence/no-improvement condition before max_rounds is reached.
    rounds = [
        _round_summary(
            retained=[
                _candidate(
                    f"cand-{i}",
                    [f"modA-{i}", f"modB-{i}"],
                    str(Decimal("0.5") + i * Decimal("0.1")),
                )
            ]
        )
        for i in range(3)
    ]
    result, calls = _run(
        rounds, orchestration_policy=_orchestration_policy(max_rounds=3), tmp_path=tmp_path
    )
    assert result.stopping_reason == StoppingReason.MAX_ROUNDS
    assert len(calls) == 3
    assert len(result.rounds) == 3


def test_stopping_reason_candidate_budget_exhausted(tmp_path):
    round1 = _round_summary(
        retained=[_candidate("cand-1", ["modA"], "0.5"), _candidate("cand-2", ["modB"], "0.4")]
    )
    result, calls = _run(
        [round1],
        orchestration_policy=_orchestration_policy(max_rounds=5, max_total_candidates=2),
        tmp_path=tmp_path,
    )
    assert result.stopping_reason == StoppingReason.CANDIDATE_BUDGET_EXHAUSTED
    assert len(calls) == 1


def test_stopping_reason_calibration_budget_exhausted(tmp_path):
    decision = _decision("cand-1", "modA")
    envelope = _request_envelope("cand-1", "modA")
    round1 = _round_summary(
        retained=[_candidate("cand-1", ["modA", "modB"], "0.5")],
        calibration_decisions=[decision],
        calibration_requests=[envelope],
    )
    result, calls = _run(
        [round1, round1],
        orchestration_policy=_orchestration_policy(max_rounds=5),
        calibration_selection_policy=_basic_policy(total_calibration_run_budget=1),
        tmp_path=tmp_path,
    )
    assert result.stopping_reason == StoppingReason.CALIBRATION_BUDGET_EXHAUSTED
    assert len(calls) == 1
    assert result.total_calibration_runs_used == 1


def test_stopping_reason_search_exhausted_when_retained_is_empty(tmp_path):
    round1 = _round_summary(retained=[])
    result, calls = _run(
        [round1], orchestration_policy=_orchestration_policy(max_rounds=5), tmp_path=tmp_path
    )
    assert result.stopping_reason == StoppingReason.SEARCH_EXHAUSTED
    assert len(calls) == 1


def test_stopping_reason_repeated_candidate_set(tmp_path):
    round_fixed = _round_summary(retained=[_candidate("cand-1", ["modA"], "0.5")])
    result, calls = _run(
        [round_fixed, round_fixed, round_fixed],
        orchestration_policy=_orchestration_policy(max_rounds=5),
        tmp_path=tmp_path,
    )
    assert result.stopping_reason == StoppingReason.REPEATED_CANDIDATE_SET
    assert len(calls) == 2


def test_stopping_reason_stable_boundary_convergence(tmp_path):
    # Different candidate ids, identical structural partition (module_ids) -- not an exact
    # repeated-candidate-set, but structurally converged.
    round1 = _round_summary(retained=[_candidate("cand-1", ["modA", "modB"], "0.5")])
    round2 = _round_summary(retained=[_candidate("cand-2", ["modA", "modB"], "0.6")])
    result, calls = _run(
        [round1, round2, round2],
        orchestration_policy=_orchestration_policy(max_rounds=5, improvement_epsilon="0.2"),
        tmp_path=tmp_path,
    )
    assert result.stopping_reason == StoppingReason.STABLE_BOUNDARY_CONVERGENCE
    assert len(calls) == 2


def test_stopping_reason_no_improvement(tmp_path):
    round1 = _round_summary(retained=[_candidate("cand-1", ["modA", "modB"], "0.50")])
    round2 = _round_summary(retained=[_candidate("cand-2", ["modA", "modC"], "0.501")])
    result, calls = _run(
        [round1, round2, round2],
        orchestration_policy=_orchestration_policy(max_rounds=5, improvement_epsilon="0.05"),
        tmp_path=tmp_path,
    )
    assert result.stopping_reason == StoppingReason.NO_IMPROVEMENT
    assert len(calls) == 2


# --- Human review gate ---------------------------------------------------------------------------


def test_human_review_gate_stops_after_one_round(tmp_path):
    round1 = _round_summary(retained=[_candidate("cand-1", ["modA"], "0.5")])
    result, calls = _run(
        [round1, round1, round1],
        orchestration_policy=_orchestration_policy(max_rounds=5, require_human_review=True),
        tmp_path=tmp_path,
    )
    assert result.stopping_reason == StoppingReason.HUMAN_REVIEW_GATE
    assert result.requires_user_review is True
    assert len(calls) == 1
    assert len(result.rounds) == 1


# --- Recursive/submodel invocation ---------------------------------------------------------------


def test_submodel_module_id_is_threaded_to_every_round(tmp_path):
    round1 = _round_summary(retained=[])
    _result, calls = _run(
        [round1],
        orchestration_policy=_orchestration_policy(max_rounds=1),
        submodel_module_id="modA",
        tmp_path=tmp_path,
    )
    assert calls[0]["submodel_module_id"] == "modA"


# --- Determinism / provenance ---------------------------------------------------------------------


def test_deterministic_repeated_execution(tmp_path):
    round1 = _round_summary(retained=[_candidate("cand-1", ["modA"], "0.5")])
    result1, _c1 = _run(
        [round1, round1],
        orchestration_policy=_orchestration_policy(max_rounds=2),
        tmp_path=tmp_path / "a",
    )
    result2, _c2 = _run(
        [round1, round1],
        orchestration_policy=_orchestration_policy(max_rounds=2),
        tmp_path=tmp_path / "b",
    )
    assert result1.stopping_reason == result2.stopping_reason
    assert len(result1.rounds) == len(result2.rounds)
    assert [r.best_overall_score for r in result1.rounds] == [
        r.best_overall_score for r in result2.rounds
    ]


def test_calibration_evidence_reverses_candidate_ranking_across_rounds(tmp_path):
    """End to end (through the orchestration loop, not just Agent 2 alone): a module's own
    negative calibration outcome, once routed and fed back, changes which candidate the *next*
    round reports as best -- confirmed here via the fake round-runner's own second-round input,
    which only a real recursive loop would ever produce."""
    decision = _decision("cand-1", "modA")
    envelope = _request_envelope("cand-1", "modA")
    round1 = _round_summary(
        retained=[
            _candidate("cand-1", ["modA", "modB"], "0.9"),
            _candidate("cand-2", ["modC", "modD"], "0.4"),
        ],
        calibration_decisions=[decision],
        calibration_requests=[envelope],
    )
    # Round 2 (post-calibration): cand-1's own module came back UNIDENTIFIABLE, flipping the
    # ranking in favor of cand-2.
    round2 = _round_summary(
        retained=[
            _candidate("cand-1", ["modA", "modB"], "0.2"),
            _candidate("cand-2", ["modC", "modD"], "0.4"),
        ]
    )

    def failing_runner(request, calibration_request, *, stage_dir, timeout_seconds=300.0):
        return _evaluation(status="UNIDENTIFIABLE", module_id=request["module_id"])

    result, calls = _run(
        [round1, round2],
        orchestration_policy=_orchestration_policy(max_rounds=2),
        calibration_runner=failing_runner,
        tmp_path=tmp_path,
    )
    assert len(calls) == 2
    # Round 2's own evidence input must carry the UNIDENTIFIABLE evaluation obtained in round 1.
    evidence_in = calls[1]["calibration_evidence"]
    assert evidence_in is not None
    assert evidence_in[0]["evaluation"]["status"] == "UNIDENTIFIABLE"
    assert result.rounds[0].best_overall_score == "0.9"
    assert result.rounds[1].best_overall_score == "0.4"
