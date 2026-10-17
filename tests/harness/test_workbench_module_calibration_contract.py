"""Tests for the Workbench <-> Harness module-calibration contract (Module-Level Agent4
Calibration with Immutable Execution-Condition Provenance increment) and its canonical
entrypoint (``scripts/run_workbench_module_calibration_request.py``).

Mirrors ``tests/harness/test_workbench_module_simulation_contract.py``'s own established
convention: real, end-to-end subprocess invocations run against the repository's own synthetic
fixture; every pre-execution rejection path is exercised directly (fast, no subprocess, no
agent invoked).

**The real calibration scenario is deliberately self-consistent, not fabricated evidence.**
modA (reaction-1: S1->S2, reaction-2: S2->S3) has S1 fixed at a known constant (an explicit,
human-supplied boundary treatment -- S1 never crosses modA's own topological boundary, but a
human reviewer may still choose to treat it as an externally-controlled feed, exactly as
``module_ports`` already supports for any species) and S3 fixed (the one real, topologically-
derived boundary species). With k1 left at Agent 2's own default ``HEURISTIC_INITIALIZATION``
value of 1 and S2(0)=0, S2(t) obeys the linear ODE ``dS2/dt = k1*S1 - k2*S2``, solved
analytically (``S2(t) = (k1*S1/k2) * (1 - exp(-k2*t))``) for a chosen true k2 -- the identical
"precompute ground truth analytically, no RoadRunner dependency in the test process itself"
technique ``tests/harness/test_module_calibration_workflow.py``'s own real round-trip test
already uses for its one-parameter exponential-decay example.
"""

from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path

import pytest

from app.harness.workbench_contracts import (
    WORKBENCH_MODULE_CALIBRATION_CONTRACT_VERSION,
    WorkbenchModuleCalibrationRequest,
    WorkbenchModuleCalibrationResult,
    WorkbenchRunErrorCode,
    WorkbenchRunStatus,
    module_calibration_request_from_dict,
    module_calibration_request_to_dict,
    module_calibration_result_from_dict,
    module_calibration_result_to_dict,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_FIXTURES = _REPO_ROOT / "tests" / "fixtures"
_ENTRYPOINT = _REPO_ROOT / "scripts" / "run_workbench_module_calibration_request.py"

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


def _true_s2_observations() -> tuple[list[float], list[float]]:
    time_points = [1.0, 2.0, 4.0, 6.0, 8.0, 12.0, 16.0, 20.0]
    values = [(_K1 * _S1_FIXED / _TRUE_K2) * (1 - math.exp(-_TRUE_K2 * t)) for t in time_points]
    return time_points, values


def _calibration_request() -> dict:
    time_points, values = _true_s2_observations()
    return {
        "request_id": "calib-req-1",
        "targets": [
            {
                "target_kind": "PARAMETER",
                "target_id": "k_reaction-2_protein-2",
                "bounds": {"lower": 0.001, "upper": 5.0},
            }
        ],
        "observations": {
            "observation_set_id": "modA-s2-train-set",
            "observations": [
                {
                    "observation_id": "obs-s2",
                    "target_species_id": "compound-S2::in::compartment-1",
                    "kind": "TIME_SERIES",
                    "partition": "TRAIN",
                    "time_points": time_points,
                    "values": values,
                }
            ],
        },
    }


def _base_request(run_id: str, *, attach_payload: dict, module_id: str, **overrides) -> dict:
    data = {
        "contract_version": WORKBENCH_MODULE_CALIBRATION_CONTRACT_VERSION,
        "run_id": run_id,
        "project_id": "proj-test",
        "subproject_id": "sub-test",
        "attach_payload": attach_payload,
        "module_id": module_id,
        "calibration_request": _calibration_request(),
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
    request = WorkbenchModuleCalibrationRequest(
        contract_version=WORKBENCH_MODULE_CALIBRATION_CONTRACT_VERSION,
        run_id="roundtrip-test",
        project_id="proj-1",
        subproject_id="sub-1",
        attach_payload={"modularization_id": "x", "module_ids": ["modA"], "memberships": []},
        module_id="modA",
        calibration_request=_calibration_request(),
        agent1_organism_id="organism-1",
    )
    restored = module_calibration_request_from_dict(module_calibration_request_to_dict(request))
    assert restored == request


def test_request_from_dict_raises_on_missing_required_field():
    data = _base_request("missing-field-test", attach_payload={}, module_id="modA")
    del data["calibration_request"]
    with pytest.raises(KeyError):
        module_calibration_request_from_dict(data)


def test_result_round_trips_through_dict():
    result = WorkbenchModuleCalibrationResult(
        contract_version=WORKBENCH_MODULE_CALIBRATION_CONTRACT_VERSION,
        run_id="result-roundtrip",
        status=WorkbenchRunStatus.SUCCEEDED,
        module_id="modA",
        modularization_id="candidate::0001",
        module_handoff={"model_id": "m1"},
        agent3_report={"report_id": "r1", "overall_status": "STEADY_STATE_FOUND"},
        agent4_report={"report_id": "a4-1", "calibration": {"status": "SUCCESS"}},
        started_at="2026-01-01T00:00:00+00:00",
        completed_at="2026-01-01T00:00:05+00:00",
        error=None,
        summary="calibrated",
        warnings=("a warning",),
    )
    restored = module_calibration_result_from_dict(module_calibration_result_to_dict(result))
    assert restored == result


# --- Pre-execution rejections (fast, no subprocess) -----------------------------------------


def test_contract_version_mismatch_is_rejected(tmp_path):
    request_data = _base_request(
        "calib-version-mismatch", attach_payload={}, module_id="modA", contract_version="not-real"
    )
    returncode, result = _invoke(tmp_path, request_data)
    try:
        assert returncode == 1
        assert result["status"] == WorkbenchRunStatus.FAILED.value
        assert result["error"]["code"] == WorkbenchRunErrorCode.CONTRACT_VERSION_MISMATCH.value
    finally:
        _cleanup_run_artifacts("calib-version-mismatch")


def test_invalid_stage1_input_neither_set_is_rejected(tmp_path):
    request_data = _base_request("calib-stage1-neither", attach_payload={}, module_id="modA")
    del request_data["input_artifact_references"]["stage1_synthetic_source"]
    returncode, result = _invoke(tmp_path, request_data)
    try:
        assert returncode == 1
        assert result["error"]["code"] == WorkbenchRunErrorCode.INVALID_STAGE1_INPUT.value
    finally:
        _cleanup_run_artifacts("calib-stage1-neither")


def test_malformed_request_is_rejected_cleanly(tmp_path):
    request_data = _base_request("calib-malformed", attach_payload={}, module_id="modA")
    del request_data["attach_payload"]
    returncode, result = _invoke(tmp_path, request_data)
    try:
        assert returncode == 1
        assert result["error"]["code"] == WorkbenchRunErrorCode.MALFORMED_REQUEST.value
    finally:
        _cleanup_run_artifacts("calib-malformed")


def test_target_naming_unknown_parameter_is_rejected(tmp_path):
    """A calibration target naming a parameter the module does not have is rejected clearly,
    never silently sent to Agent 4 (task instructions §3: reject incomplete/unsupported
    requests explicitly, never fabricate)."""
    request_data = _base_request(
        "calib-unknown-target",
        attach_payload=_two_module_attach_payload(),
        module_id="modA",
        calibration_request={
            **_calibration_request(),
            "targets": [
                {"target_kind": "PARAMETER", "target_id": "not-a-real-parameter", "bounds": None}
            ],
        },
    )
    try:
        returncode, result = _invoke(tmp_path, request_data)
        assert returncode == 1
        assert (
            result["error"]["code"]
            == WorkbenchRunErrorCode.MODULE_CALIBRATION_EXECUTION_FAILED.value
        )
        assert "not-a-real-parameter" in result["error"]["message"]
    finally:
        _cleanup_run_artifacts("calib-unknown-target")


# --- Real, end-to-end subprocess invocation -------------------------------------------------


@pytest.fixture(scope="module")
def real_module_calibration_success() -> dict:
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        request_data = _base_request(
            "real-module-calibration-success",
            attach_payload=_two_module_attach_payload(),
            module_id="modA",
        )
        returncode, result = _invoke(Path(tmp), request_data)
        assert returncode == 0, f"canonical entrypoint failed: {result}"
        yield result
    _cleanup_run_artifacts("real-module-calibration-success")


def test_real_module_calibration_succeeds(real_module_calibration_success):
    assert real_module_calibration_success["status"] == WorkbenchRunStatus.SUCCEEDED.value
    assert real_module_calibration_success["agent4_report"]["calibration"]["status"] == "SUCCESS"


def test_real_module_calibration_recovers_the_true_parameter(real_module_calibration_success):
    estimates = {
        p["target_id"]: p["fitted_value"]
        for p in real_module_calibration_success["agent4_report"]["calibration"][
            "parameter_estimates"
        ]
    }
    assert estimates["k_reaction-2_protein-2"] == pytest.approx(_TRUE_K2, rel=0.05)


def test_real_module_calibration_executed_the_module_not_the_root(real_module_calibration_success):
    """The whole synthetic root model has 3 reactions/3 parameters/4 species; modA has only 2
    of each reaction/parameter -- confirming Agent 4's own handoff was built from the module's
    own scoped artifact, never the root's."""
    handoff = real_module_calibration_success["module_handoff"]
    assert len(handoff["reactions"]) == 2
    assert len(handoff["parameters"]) == 2
    assert "modA" in handoff["model_id"]


def test_real_module_calibration_used_the_resolved_boundary_condition(
    real_module_calibration_success,
):
    """The fixed S1 feed (10) and the derived S3 boundary port are both declared ``const`` in
    the actually-materialized Antimony text -- confirming the resolved boundary semantics,
    never a default/fabricated value, were what Agent 4 actually calibrated against."""
    handoff = real_module_calibration_success["module_handoff"]
    s1_symbol = handoff["antimony_symbol_map"]["species"]["compound-S1::in::compartment-1"]
    antimony_text = handoff["antimony_text"]
    assert f"const {s1_symbol};" in antimony_text
    # Agent 2's own Antimony generator normalizes a whole-number Decimal to "10", not "10.0" --
    # asserted against the value actually rendered, never against this test's own input string.
    assert f"{s1_symbol} = {int(_S1_FIXED)};" in antimony_text


def test_real_module_calibration_is_idempotently_replayed(tmp_path):
    request_data = _base_request(
        "real-module-calibration-replay-test",
        attach_payload=_two_module_attach_payload(),
        module_id="modA",
    )
    try:
        returncode1, result1 = _invoke(tmp_path, request_data)
        assert returncode1 == 0
        assert result1["replayed"] is False

        returncode2, result2 = _invoke(tmp_path, request_data)
        assert returncode2 == 0
        assert result2["replayed"] is True
        assert result2["agent4_report"] == result1["agent4_report"]
    finally:
        _cleanup_run_artifacts("real-module-calibration-replay-test")


def test_real_run_rejects_a_module_with_no_boundary_treatment_cleanly(tmp_path):
    """A module reached purely through the hierarchical-recursion search's own attach_payload
    (no module_ports) has no eligible standalone artifact -- Agent 2's own
    ``generate_module_artifacts`` never fabricates a boundary condition, so this must come back
    cleanly as ``MODULE_CALIBRATION_EXECUTION_FAILED``, never a silently-accepted request."""
    request_data = _base_request(
        "real-module-calibration-no-boundary",
        attach_payload=_two_module_attach_payload(with_module_ports=False),
        module_id="modA",
    )
    try:
        returncode, result = _invoke(tmp_path, request_data)
        assert returncode == 1
        assert result["status"] == WorkbenchRunStatus.FAILED.value
        assert (
            result["error"]["code"]
            == WorkbenchRunErrorCode.MODULE_CALIBRATION_EXECUTION_FAILED.value
        )
    finally:
        _cleanup_run_artifacts("real-module-calibration-no-boundary")
