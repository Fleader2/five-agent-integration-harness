"""Tests for the Workbench <-> Harness whole-model experimental-scenario-evaluation contract
(Whole-Model Experimental-Scenario Evaluation increment) and its canonical entrypoint
(``scripts/run_workbench_model_scenario_evaluation_request.py``).

Mirrors ``tests/harness/test_workbench_model_antimony_verification_contract.py``'s own
established convention: real, end-to-end subprocess invocations (one real Agent 3 round, via
its own ``antimony``/``roadrunner`` dependencies) rather than a mocked loader. This contract
takes Antimony text directly -- Agent 2 is never invoked here, and neither is Agent 4 (this is
prediction, never fitting), so a short, literal, hand-written Antimony string is real and
sufficient for every test in this file.
"""

from __future__ import annotations

import json
import math
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from app.harness.workbench_contracts import (
    WORKBENCH_MODEL_SCENARIO_EVALUATION_CONTRACT_VERSION,
    WorkbenchModelScenarioEvaluationRequest,
    WorkbenchModelScenarioEvaluationResult,
    WorkbenchRunErrorCode,
    WorkbenchRunStatus,
    WorkbenchStepIntervention,
    model_scenario_evaluation_request_from_dict,
    model_scenario_evaluation_request_to_dict,
    model_scenario_evaluation_result_from_dict,
    model_scenario_evaluation_result_to_dict,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_ENTRYPOINT = _REPO_ROOT / "scripts" / "run_workbench_model_scenario_evaluation_request.py"

#: Exact exponential decay (ds/dt = -k*s) -- every prediction below is checked against this
#: closed-form value, never just "the solver returned something."
_DECAY_ANTIMONY_TEXT = """
model decay_model
  compartment C1
  C1 = 1.0
  species S1 in C1
  S1 = 10
  J1: S1 ->; k1 * S1
  k1 = 0.5
end
"""


def _decay(s0: float, k: float, t: float) -> float:
    return s0 * math.exp(-k * t)


def _base_request(run_id: str, *, antimony_text: str, **overrides) -> dict:
    data = {
        "contract_version": WORKBENCH_MODEL_SCENARIO_EVALUATION_CONTRACT_VERSION,
        "run_id": run_id,
        "antimony_text": antimony_text,
        "requested_times": [0.0, 1.0, 2.0],
        "requested_output_ids": ["S1"],
    }
    data.update(overrides)
    return data


def _invoke(tmp_path: Path, request_data: dict) -> tuple[int, dict]:
    request_path = tmp_path / "request.json"
    output_path = tmp_path / "result.json"
    request_path.write_text(json.dumps(request_data))
    proc = subprocess.run(
        [
            sys.executable,
            str(_ENTRYPOINT),
            "--request",
            str(request_path),
            "--output",
            str(output_path),
        ],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=300,
    )
    result_data = json.loads(output_path.read_text()) if output_path.is_file() else None
    return proc.returncode, result_data


def _cleanup_run_artifacts(run_id: str) -> None:
    run_dir = _REPO_ROOT / "artifacts" / "runs" / run_id
    if run_dir.is_dir():
        shutil.rmtree(run_dir)


# --- Contract serialization/deserialization ------------------------------------------------


def test_request_round_trips_through_dict():
    request = WorkbenchModelScenarioEvaluationRequest(
        contract_version=WORKBENCH_MODEL_SCENARIO_EVALUATION_CONTRACT_VERSION,
        run_id="roundtrip-test",
        antimony_text=_DECAY_ANTIMONY_TEXT,
        requested_times=(0.0, 1.0, 5.0),
        requested_output_ids=("S1",),
        parameter_overrides={"k1": 2.0},
        initial_value_overrides={"S1": 50.0},
        interventions=(
            WorkbenchStepIntervention(
                target_kind="SPECIES", target_id="S1", time=3.0, value=100.0
            ),
        ),
        correlation_id="corr-1",
        submitted_at="2026-01-01T00:00:00+00:00",
    )
    restored = model_scenario_evaluation_request_from_dict(
        model_scenario_evaluation_request_to_dict(request)
    )
    assert restored == request


def test_result_round_trips_through_dict():
    result = WorkbenchModelScenarioEvaluationResult(
        contract_version=WORKBENCH_MODEL_SCENARIO_EVALUATION_CONTRACT_VERSION,
        run_id="result-roundtrip",
        status=WorkbenchRunStatus.SUCCEEDED,
        evaluation_status="SUCCESS",
        predictions={"S1": (10.0, 6.065, 3.679)},
        validation_errors=(),
        solver_message=None,
        antimony_version="3.2.0",
        roadrunner_version="2.10.0",
        started_at="2026-01-01T00:00:00+00:00",
        completed_at="2026-01-01T00:00:05+00:00",
        error=None,
        summary="evaluated",
    )
    restored = model_scenario_evaluation_result_from_dict(
        model_scenario_evaluation_result_to_dict(result)
    )
    assert restored == result


# --- Pre-execution rejections (fast, no subprocess) -----------------------------------------


def test_contract_version_mismatch_is_rejected(tmp_path):
    run_id = "scenario-eval-version-mismatch"
    try:
        request_data = _base_request(
            run_id, antimony_text=_DECAY_ANTIMONY_TEXT, contract_version="not-real"
        )
        returncode, result = _invoke(tmp_path, request_data)
        assert returncode == 1
        assert result["error"]["code"] == WorkbenchRunErrorCode.CONTRACT_VERSION_MISMATCH.value
    finally:
        _cleanup_run_artifacts(run_id)


def test_malformed_request_missing_requested_times_is_rejected(tmp_path):
    request_path = tmp_path / "request.json"
    output_path = tmp_path / "result.json"
    request_path.write_text(
        json.dumps(
            {
                "contract_version": WORKBENCH_MODEL_SCENARIO_EVALUATION_CONTRACT_VERSION,
                "run_id": "scenario-eval-missing-field",
                "antimony_text": _DECAY_ANTIMONY_TEXT,
                "requested_output_ids": ["S1"],
            }
        )
    )
    proc = subprocess.run(
        [
            sys.executable,
            str(_ENTRYPOINT),
            "--request",
            str(request_path),
            "--output",
            str(output_path),
        ],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    try:
        assert proc.returncode == 1
        result = json.loads(output_path.read_text())
        assert result["error"]["code"] == WorkbenchRunErrorCode.MALFORMED_REQUEST.value
    finally:
        _cleanup_run_artifacts("scenario-eval-missing-field")


# --- Real, end-to-end subprocess invocation (real Agent 3 antimony/roadrunner simulation) ---


def test_a_valid_scenario_evaluates_and_matches_the_analytic_decay_solution(tmp_path):
    run_id = "scenario-eval-valid-decay"
    try:
        request_data = _base_request(run_id, antimony_text=_DECAY_ANTIMONY_TEXT)
        returncode, result = _invoke(tmp_path, request_data)
        assert returncode == 0, f"canonical entrypoint failed: {result}"
        assert result["status"] == WorkbenchRunStatus.SUCCEEDED.value
        assert result["evaluation_status"] == "SUCCESS"
        predictions = result["predictions"]["S1"]
        for t, predicted in zip([0.0, 1.0, 2.0], predictions, strict=True):
            assert predicted == pytest.approx(_decay(10.0, 0.5, t))
    finally:
        _cleanup_run_artifacts(run_id)


def test_a_candidate_parameter_value_changes_the_predicted_trajectory(tmp_path):
    run_id = "scenario-eval-parameter-override"
    try:
        request_data = _base_request(
            run_id,
            antimony_text=_DECAY_ANTIMONY_TEXT,
            parameter_overrides={"k1": 2.0},
            requested_times=[1.0],
        )
        returncode, result = _invoke(tmp_path, request_data)
        assert returncode == 0, f"canonical entrypoint failed: {result}"
        assert result["predictions"]["S1"][0] == pytest.approx(_decay(10.0, 2.0, 1.0))
    finally:
        _cleanup_run_artifacts(run_id)


def test_a_step_intervention_changes_the_trajectory_from_its_own_declared_time(tmp_path):
    run_id = "scenario-eval-intervention"
    try:
        request_data = _base_request(
            run_id,
            antimony_text=_DECAY_ANTIMONY_TEXT,
            requested_times=[5.0, 6.0],
            interventions=[
                {"target_kind": "SPECIES", "target_id": "S1", "time": 5.0, "value": 100.0}
            ],
        )
        returncode, result = _invoke(tmp_path, request_data)
        assert returncode == 0, f"canonical entrypoint failed: {result}"
        predictions = result["predictions"]["S1"]
        # Reported at t=5 is the state immediately before the intervention takes effect.
        assert predictions[0] == pytest.approx(_decay(10.0, 0.5, 5.0))
        # One second of decay from the post-intervention value of 100.
        assert predictions[1] == pytest.approx(_decay(100.0, 0.5, 1.0))
    finally:
        _cleanup_run_artifacts(run_id)


def test_different_fixed_doses_produce_distinct_predictions_from_the_same_model(tmp_path):
    """The exact "different fixed doses/conditions" scenario the task requires: calling the
    evaluation twice with different resolved scenario inputs against the same model."""
    run_id_a = "scenario-eval-dose-a"
    run_id_b = "scenario-eval-dose-b"
    try:
        _, result_a = _invoke(
            tmp_path,
            _base_request(
                run_id_a,
                antimony_text=_DECAY_ANTIMONY_TEXT,
                initial_value_overrides={"S1": 10.0},
                requested_times=[1.0],
            ),
        )
        _, result_b = _invoke(
            tmp_path,
            _base_request(
                run_id_b,
                antimony_text=_DECAY_ANTIMONY_TEXT,
                initial_value_overrides={"S1": 1000.0},
                requested_times=[1.0],
            ),
        )
        assert result_a["predictions"]["S1"][0] != result_b["predictions"]["S1"][0]
        assert result_a["predictions"]["S1"][0] == pytest.approx(_decay(10.0, 0.5, 1.0))
        assert result_b["predictions"]["S1"][0] == pytest.approx(_decay(1000.0, 0.5, 1.0))
    finally:
        _cleanup_run_artifacts(run_id_a)
        _cleanup_run_artifacts(run_id_b)


def test_an_unresolved_identifier_is_a_disclosed_invalid_request_not_an_infrastructure_failure(
    tmp_path,
):
    run_id = "scenario-eval-unresolved-identifier"
    try:
        request_data = _base_request(
            run_id,
            antimony_text=_DECAY_ANTIMONY_TEXT,
            parameter_overrides={"not_a_real_parameter": 1.0},
        )
        returncode, result = _invoke(tmp_path, request_data)
        assert returncode == 0, f"canonical entrypoint failed: {result}"
        assert result["status"] == WorkbenchRunStatus.SUCCEEDED.value
        assert result["evaluation_status"] == "INVALID_REQUEST"
        assert any("not_a_real_parameter" in e for e in result["validation_errors"])
        assert result["predictions"] is None
    finally:
        _cleanup_run_artifacts(run_id)


def test_malformed_antimony_text_reports_model_load_failed_not_an_infrastructure_error(tmp_path):
    run_id = "scenario-eval-malformed-antimony"
    try:
        request_data = _base_request(run_id, antimony_text="this is not valid antimony !!!")
        returncode, result = _invoke(tmp_path, request_data)
        assert returncode == 0, f"canonical entrypoint failed: {result}"
        assert result["status"] == WorkbenchRunStatus.SUCCEEDED.value
        assert result["evaluation_status"] == "MODEL_LOAD_FAILED"
        assert result["predictions"] is None
    finally:
        _cleanup_run_artifacts(run_id)


def test_a_second_call_with_the_identical_run_id_replays_rather_than_reevaluating(tmp_path):
    run_id = "scenario-eval-replay"
    try:
        request_data = _base_request(run_id, antimony_text=_DECAY_ANTIMONY_TEXT)
        first_returncode, first_result = _invoke(tmp_path, request_data)
        assert first_returncode == 0
        assert first_result["replayed"] is False

        second_returncode, second_result = _invoke(tmp_path, request_data)
        assert second_returncode == 0
        assert second_result["replayed"] is True
        assert second_result["predictions"] == first_result["predictions"]
    finally:
        _cleanup_run_artifacts(run_id)


