"""Tests for the Workbench <-> Harness module-validation contract (Module-Level Agent5
Validation and Experimental Design increment) and its canonical entrypoint
(``scripts/run_workbench_module_validation_request.py``).

Mirrors ``tests/harness/test_workbench_module_calibration_contract.py``'s own established
convention: real, end-to-end subprocess invocations run against the repository's own synthetic
fixture; every pre-execution rejection path is exercised directly (fast, no subprocess, no
agent invoked).

**The real validation scenario continues directly from the calibration contract's own real
scenario.** A real module-calibration execution (``app.harness.module_calibration_execution
.run_module_calibration_execution_workflow``, invoked in-process here, not re-derived by hand)
produces a genuine ``agent4_report`` with a real fitted ``k_reaction-2_protein-2`` -- that
report, never a hand-crafted stand-in, is what this contract's own real test hands to Agent 5,
alongside a *second*, independent set of synthetic observations (different time points, same
underlying true dynamics) -- the identical "analytically-precomputed ground truth, no
RoadRunner dependency in the test process itself" technique used throughout this family.
"""

from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path

import pytest

from app.harness.module_calibration_execution import run_module_calibration_execution_workflow
from app.harness.workbench_contracts import (
    WORKBENCH_MODULE_VALIDATION_CONTRACT_VERSION,
    WorkbenchModuleValidationRequest,
    WorkbenchModuleValidationResult,
    WorkbenchRunErrorCode,
    WorkbenchRunStatus,
    module_validation_request_from_dict,
    module_validation_request_to_dict,
    module_validation_result_from_dict,
    module_validation_result_to_dict,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_FIXTURES = _REPO_ROOT / "tests" / "fixtures"
_ENTRYPOINT = _REPO_ROOT / "scripts" / "run_workbench_module_validation_request.py"

_K1 = 1.0
_S1_FIXED = 10.0
_TRUE_K2 = 0.5


def _two_module_attach_payload(*, with_module_ports: bool = True) -> dict:
    modularization_id = "candidate::manual::0001"
    reactions = ["reaction-1", "reaction-2", "reaction-3"]
    params = ["k_reaction-1_protein-1", "k_reaction-2_protein-2", "k_reaction-3_protein-3"]
    species = [
        "compound-S1::in::compartment-1",
        "compound-S2::in::compartment-1",
        "compound-S3::in::compartment-1",
        "compound-S4::in::compartment-1",
    ]
    memberships = []
    for r in reactions:
        target = "modA" if r in ("reaction-1", "reaction-2") else "modB"
        memberships.append({"module_id": target, "component_type": "REACTION", "component_id": r})
    for p in params:
        target = "modA" if ("reaction-1" in p or "reaction-2" in p) else "modB"
        memberships.append({"module_id": target, "component_type": "PARAMETER", "component_id": p})
    for s in species:
        memberships.append({"module_id": "modA", "component_type": "SPECIES", "component_id": s})
        memberships.append({"module_id": "modB", "component_type": "SPECIES", "component_id": s})
    payload = {
        "modularization_id": modularization_id,
        "module_ids": ["modA", "modB"],
        "memberships": memberships,
    }
    if with_module_ports:
        payload["module_ports"] = [
            {
                "port_id": "port::modA::S1",
                "module_id": "modA",
                "species_id": "compound-S1::in::compartment-1",
                "direction": "INPUT",
                "externally_controlled": True,
                "initial_value": str(_S1_FIXED),
            },
            {
                "port_id": "port::modA::S3",
                "module_id": "modA",
                "species_id": "compound-S3::in::compartment-1",
                "direction": "OUTPUT",
                "externally_controlled": True,
                "initial_value": "0",
            },
        ]
    return payload


def _s2_trajectory(time_points: list[float]) -> list[float]:
    return [(_K1 * _S1_FIXED / _TRUE_K2) * (1 - math.exp(-_TRUE_K2 * t)) for t in time_points]


def _real_agent4_report(run_id: str) -> dict:
    """A genuine, real ``agent4_report`` for modA -- produced by a real Agent2->Agent3->Agent4
    round trip, never hand-crafted."""
    train_t = [1.0, 2.0, 4.0, 6.0, 8.0, 12.0, 16.0, 20.0]
    calib_result = run_module_calibration_execution_workflow(
        {
            "run_id": run_id,
            "agent1_view_path": str(_FIXTURES / "synthetic_agent1_view.json"),
            "attach_payload": _two_module_attach_payload(),
            "module_id": "modA",
            "correlation_id": run_id,
        },
        {
            "request_id": f"calib-req-{run_id}",
            "targets": [
                {
                    "target_kind": "PARAMETER",
                    "target_id": "k_reaction-2_protein-2",
                    "bounds": {"lower": 0.001, "upper": 5.0},
                }
            ],
            "observations": {
                "observation_set_id": "modA-s2-train",
                "observations": [
                    {
                        "observation_id": "obs-train",
                        "target_species_id": "compound-S2::in::compartment-1",
                        "kind": "TIME_SERIES",
                        "partition": "TRAIN",
                        "time_points": train_t,
                        "values": _s2_trajectory(train_t),
                    }
                ],
            },
        },
        stage_dir=_REPO_ROOT / "artifacts" / "runs" / run_id,
    )
    assert calib_result["agent4_report"]["calibration"]["status"] == "SUCCESS"
    return calib_result["agent4_report"]


def _validation_request() -> dict:
    val_t = [3.0, 10.0, 18.0]
    return {
        "request_id": "val-req-1",
        "validation_observations": {
            "observation_set_id": "modA-s2-held-out",
            "observations": [
                {
                    "observation_id": "obs-val",
                    "target_species_id": "compound-S2::in::compartment-1",
                    "kind": "TIME_SERIES",
                    "time_points": val_t,
                    "values": _s2_trajectory(val_t),
                }
            ],
        },
    }


def _base_request(
    run_id: str, *, attach_payload: dict, module_id: str, agent4_report: dict, **overrides
) -> dict:
    data = {
        "contract_version": WORKBENCH_MODULE_VALIDATION_CONTRACT_VERSION,
        "run_id": run_id,
        "project_id": "proj-test",
        "subproject_id": "sub-test",
        "attach_payload": attach_payload,
        "module_id": module_id,
        "agent4_report": agent4_report,
        "validation_request": _validation_request(),
        "input_artifact_references": {
            "stage1_synthetic_source": str(_FIXTURES / "synthetic_agent1_view.json"),
        },
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
    import shutil

    run_dir = _REPO_ROOT / "artifacts" / "runs" / run_id
    if run_dir.is_dir():
        shutil.rmtree(run_dir)


# --- Contract serialization/deserialization ------------------------------------------------


def test_request_round_trips_through_dict():
    request = WorkbenchModuleValidationRequest(
        contract_version=WORKBENCH_MODULE_VALIDATION_CONTRACT_VERSION,
        run_id="roundtrip-test",
        project_id="proj-1",
        subproject_id="sub-1",
        attach_payload={"modularization_id": "x", "module_ids": ["modA"], "memberships": []},
        module_id="modA",
        agent4_report={"report_id": "a4-1"},
        validation_request=_validation_request(),
        agent1_organism_id="organism-1",
    )
    restored = module_validation_request_from_dict(module_validation_request_to_dict(request))
    assert restored == request


def test_request_from_dict_raises_on_missing_required_field():
    data = _base_request(
        "missing-field-test", attach_payload={}, module_id="modA", agent4_report={"report_id": "a4"}
    )
    del data["validation_request"]
    with pytest.raises(KeyError):
        module_validation_request_from_dict(data)


def test_result_round_trips_through_dict():
    result = WorkbenchModuleValidationResult(
        contract_version=WORKBENCH_MODULE_VALIDATION_CONTRACT_VERSION,
        run_id="result-roundtrip",
        status=WorkbenchRunStatus.SUCCEEDED,
        module_id="modA",
        modularization_id="candidate::0001",
        module_handoff={"model_id": "m1"},
        agent5_report={"report_id": "a5-1", "overall_status": "SUCCESS"},
        started_at="2026-01-01T00:00:00+00:00",
        completed_at="2026-01-01T00:00:05+00:00",
        error=None,
        summary="validated",
        warnings=("a warning",),
    )
    restored = module_validation_result_from_dict(module_validation_result_to_dict(result))
    assert restored == result


# --- Pre-execution rejections (fast, no subprocess) -----------------------------------------


def test_contract_version_mismatch_is_rejected(tmp_path):
    request_data = _base_request(
        "val-version-mismatch",
        attach_payload={},
        module_id="modA",
        agent4_report={"report_id": "a4"},
        contract_version="not-real",
    )
    returncode, result = _invoke(tmp_path, request_data)
    try:
        assert returncode == 1
        assert result["status"] == WorkbenchRunStatus.FAILED.value
        assert result["error"]["code"] == WorkbenchRunErrorCode.CONTRACT_VERSION_MISMATCH.value
    finally:
        _cleanup_run_artifacts("val-version-mismatch")


def test_invalid_stage1_input_neither_set_is_rejected(tmp_path):
    request_data = _base_request(
        "val-stage1-neither", attach_payload={}, module_id="modA", agent4_report={"report_id": "a4"}
    )
    del request_data["input_artifact_references"]["stage1_synthetic_source"]
    returncode, result = _invoke(tmp_path, request_data)
    try:
        assert returncode == 1
        assert result["error"]["code"] == WorkbenchRunErrorCode.INVALID_STAGE1_INPUT.value
    finally:
        _cleanup_run_artifacts("val-stage1-neither")


def test_malformed_request_is_rejected_cleanly(tmp_path):
    request_data = _base_request(
        "val-malformed", attach_payload={}, module_id="modA", agent4_report={"report_id": "a4"}
    )
    del request_data["attach_payload"]
    returncode, result = _invoke(tmp_path, request_data)
    try:
        assert returncode == 1
        assert result["error"]["code"] == WorkbenchRunErrorCode.MALFORMED_REQUEST.value
    finally:
        _cleanup_run_artifacts("val-malformed")


def test_observation_naming_unknown_species_is_rejected(tmp_path):
    """A validation observation naming a species the module does not have is rejected clearly,
    never silently sent to Agent 5 (task instructions §2)."""
    bad_validation_request = {
        **_validation_request(),
        "validation_observations": {
            "observation_set_id": "bad",
            "observations": [
                {
                    "observation_id": "obs-bad",
                    "target_species_id": "not-a-real-species",
                    "kind": "TIME_SERIES",
                    "time_points": [1.0],
                    "values": [1.0],
                }
            ],
        },
    }
    request_data = _base_request(
        "val-unknown-species",
        attach_payload=_two_module_attach_payload(),
        module_id="modA",
        agent4_report={"report_id": "a4"},
        validation_request=bad_validation_request,
    )
    try:
        returncode, result = _invoke(tmp_path, request_data)
        assert returncode == 1
        assert (
            result["error"]["code"]
            == WorkbenchRunErrorCode.MODULE_VALIDATION_EXECUTION_FAILED.value
        )
        assert "not-a-real-species" in result["error"]["message"]
    finally:
        _cleanup_run_artifacts("val-unknown-species")


# --- Real, end-to-end subprocess invocation -------------------------------------------------


@pytest.fixture(scope="module")
def real_module_validation_success() -> dict:
    import tempfile

    agent4_report = _real_agent4_report("real-module-validation-calib-source")
    try:
        with tempfile.TemporaryDirectory() as tmp:
            request_data = _base_request(
                "real-module-validation-success",
                attach_payload=_two_module_attach_payload(),
                module_id="modA",
                agent4_report=agent4_report,
            )
            returncode, result = _invoke(Path(tmp), request_data)
            assert returncode == 0, f"canonical entrypoint failed: {result}"
            yield result
    finally:
        _cleanup_run_artifacts("real-module-validation-calib-source")
        _cleanup_run_artifacts("real-module-validation-success")


def test_real_module_validation_succeeds(real_module_validation_success):
    assert real_module_validation_success["status"] == WorkbenchRunStatus.SUCCEEDED.value
    assert real_module_validation_success["agent5_report"]["overall_status"] == "SUCCESS"


def test_real_module_validation_used_the_correct_calibrated_parameter(
    real_module_validation_success,
):
    checked = real_module_validation_success["agent5_report"]["calibrated_parameter_ids_checked"]
    assert "k_reaction-2_protein-2" in checked


def test_real_module_validation_against_independent_observations_has_low_residuals(
    real_module_validation_success,
):
    """The held-out observations were generated from the identical true k2 the calibration
    itself recovered -- a genuinely generalizing fit should show small validation residuals,
    confirming Agent 5 actually used the real fitted parameter, never a default/placeholder."""
    validation = real_module_validation_success["agent5_report"]["validation"]
    assert validation is not None
    assert validation["simulated"] is True
    (residual_summary,) = validation["validation_residuals"]
    assert residual_summary["sum_squared_residual"] < 0.01


def test_real_module_validation_executed_the_module_not_the_root(real_module_validation_success):
    handoff = real_module_validation_success["module_handoff"]
    assert len(handoff["reactions"]) == 2
    assert len(handoff["parameters"]) == 2
    assert "modA" in handoff["model_id"]


def test_real_module_validation_is_idempotently_replayed(tmp_path):
    agent4_report = _real_agent4_report("real-module-validation-replay-calib-source")
    try:
        request_data = _base_request(
            "real-module-validation-replay-test",
            attach_payload=_two_module_attach_payload(),
            module_id="modA",
            agent4_report=agent4_report,
        )
        returncode1, result1 = _invoke(tmp_path, request_data)
        assert returncode1 == 0
        assert result1["replayed"] is False

        returncode2, result2 = _invoke(tmp_path, request_data)
        assert returncode2 == 0
        assert result2["replayed"] is True
        assert result2["agent5_report"] == result1["agent5_report"]
    finally:
        _cleanup_run_artifacts("real-module-validation-replay-calib-source")
        _cleanup_run_artifacts("real-module-validation-replay-test")
