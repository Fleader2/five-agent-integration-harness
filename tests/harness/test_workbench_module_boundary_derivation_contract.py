"""Tests for the Workbench <-> Harness module-boundary-derivation contract
(Boundary-Condition Semantics increment) and its canonical entrypoint
(``scripts/run_workbench_module_boundary_derivation_request.py``).

Mirrors ``tests/harness/test_workbench_module_simulation_contract.py``'s own established
convention: real, end-to-end subprocess invocations run against the repository's own synthetic
fixture; every pre-execution rejection path is exercised directly (fast, no subprocess, no
agent invoked).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.harness.workbench_contracts import (
    WORKBENCH_MODULE_BOUNDARY_DERIVATION_CONTRACT_VERSION,
    WorkbenchModuleBoundaryDerivationRequest,
    WorkbenchModuleBoundaryDerivationResult,
    WorkbenchRunErrorCode,
    WorkbenchRunStatus,
    module_boundary_derivation_request_from_dict,
    module_boundary_derivation_request_to_dict,
    module_boundary_derivation_result_from_dict,
    module_boundary_derivation_result_to_dict,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_FIXTURES = _REPO_ROOT / "tests" / "fixtures"
_ENTRYPOINT = _REPO_ROOT / "scripts" / "run_workbench_module_boundary_derivation_request.py"


def _two_module_attach_payload() -> dict:
    """The identical hand-built two-module split of the synthetic fixture's own three
    reactions used throughout this harness's own module-simulation/materialization tests
    (reaction-1, reaction-2 -> modA; reaction-3 -> modB) -- deliberately with no
    ``module_ports`` entry, since this contract only ever reports structural candidates, never
    a treatment decision."""
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
    return {
        "modularization_id": modularization_id,
        "module_ids": ["modA", "modB"],
        "memberships": memberships,
    }


def _base_request(run_id: str, *, attach_payload: dict, module_id: str, **overrides) -> dict:
    data = {
        "contract_version": WORKBENCH_MODULE_BOUNDARY_DERIVATION_CONTRACT_VERSION,
        "run_id": run_id,
        "project_id": "proj-test",
        "subproject_id": "sub-test",
        "attach_payload": attach_payload,
        "module_id": module_id,
        "input_artifact_references": {
            "stage1_synthetic_source": str(_FIXTURES / "synthetic_agent1_view.json"),
        },
    }
    data.update(overrides)
    return data


def _invoke(entrypoint: Path, tmp_path: Path, request_data: dict) -> tuple[int, dict]:
    request_path = tmp_path / "request.json"
    output_path = tmp_path / "result.json"
    request_path.write_text(json.dumps(request_data))
    proc = subprocess.run(
        [
            sys.executable,
            str(entrypoint),
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
    request = WorkbenchModuleBoundaryDerivationRequest(
        contract_version=WORKBENCH_MODULE_BOUNDARY_DERIVATION_CONTRACT_VERSION,
        run_id="roundtrip-test",
        project_id="proj-1",
        subproject_id="sub-1",
        attach_payload={"modularization_id": "x", "module_ids": ["modA"], "memberships": []},
        module_id="modA",
        agent1_organism_id="organism-1",
    )
    restored = module_boundary_derivation_request_from_dict(
        module_boundary_derivation_request_to_dict(request)
    )
    assert restored == request


def test_request_from_dict_raises_on_missing_required_field():
    data = _base_request("missing-field-test", attach_payload={}, module_id="modA")
    del data["module_id"]
    with pytest.raises(KeyError):
        module_boundary_derivation_request_from_dict(data)


def test_result_round_trips_through_dict():
    result = WorkbenchModuleBoundaryDerivationResult(
        contract_version=WORKBENCH_MODULE_BOUNDARY_DERIVATION_CONTRACT_VERSION,
        run_id="result-roundtrip",
        status=WorkbenchRunStatus.SUCCEEDED,
        module_id="modA",
        candidates=({"species_id": "compound-S3::in::compartment-1", "direction": "OUTPUT"},),
        started_at="2026-01-01T00:00:00+00:00",
        completed_at="2026-01-01T00:00:05+00:00",
        error=None,
        summary="1 candidate boundary species found",
        warnings=("a warning",),
    )
    restored = module_boundary_derivation_result_from_dict(
        module_boundary_derivation_result_to_dict(result)
    )
    assert restored == result


# --- Pre-execution rejections (fast, no subprocess) -----------------------------------------


def test_contract_version_mismatch_is_rejected(tmp_path):
    request_data = _base_request(
        "boundary-version-mismatch",
        attach_payload={},
        module_id="modA",
        contract_version="not-real",
    )
    returncode, result = _invoke(_ENTRYPOINT, tmp_path, request_data)
    try:
        assert returncode == 1
        assert result["status"] == WorkbenchRunStatus.FAILED.value
        assert result["error"]["code"] == WorkbenchRunErrorCode.CONTRACT_VERSION_MISMATCH.value
    finally:
        _cleanup_run_artifacts("boundary-version-mismatch")


def test_invalid_stage1_input_neither_set_is_rejected(tmp_path):
    request_data = _base_request("boundary-stage1-neither", attach_payload={}, module_id="modA")
    del request_data["input_artifact_references"]["stage1_synthetic_source"]
    returncode, result = _invoke(_ENTRYPOINT, tmp_path, request_data)
    try:
        assert returncode == 1
        assert result["error"]["code"] == WorkbenchRunErrorCode.INVALID_STAGE1_INPUT.value
    finally:
        _cleanup_run_artifacts("boundary-stage1-neither")


def test_missing_synthetic_source_artifact_is_rejected(tmp_path):
    request_data = _base_request(
        "boundary-missing-synthetic-source",
        attach_payload={},
        module_id="modA",
        input_artifact_references={"stage1_synthetic_source": str(tmp_path / "nope.json")},
    )
    returncode, result = _invoke(_ENTRYPOINT, tmp_path, request_data)
    try:
        assert returncode == 1
        assert result["error"]["code"] == WorkbenchRunErrorCode.MISSING_INPUT_ARTIFACT.value
    finally:
        _cleanup_run_artifacts("boundary-missing-synthetic-source")


def test_malformed_request_is_rejected_cleanly(tmp_path):
    request_data = _base_request("boundary-malformed", attach_payload={}, module_id="modA")
    del request_data["attach_payload"]
    returncode, result = _invoke(_ENTRYPOINT, tmp_path, request_data)
    try:
        assert returncode == 1
        assert result["error"]["code"] == WorkbenchRunErrorCode.MALFORMED_REQUEST.value
    finally:
        _cleanup_run_artifacts("boundary-malformed")


# --- Real, end-to-end subprocess invocation -------------------------------------------------


@pytest.fixture(scope="module")
def real_boundary_derivation_modA() -> dict:
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        request_data = _base_request(
            "real-boundary-derivation-modA",
            attach_payload=_two_module_attach_payload(),
            module_id="modA",
        )
        returncode, result = _invoke(_ENTRYPOINT, Path(tmp), request_data)
        assert returncode == 0, f"canonical entrypoint failed: {result}"
        yield result
    _cleanup_run_artifacts("real-boundary-derivation-modA")


def test_real_boundary_derivation_succeeds(real_boundary_derivation_modA):
    assert real_boundary_derivation_modA["status"] == WorkbenchRunStatus.SUCCEEDED.value


def test_real_boundary_derivation_finds_the_correct_single_crossing_species(
    real_boundary_derivation_modA,
):
    """modA owns reaction-1 (S1->S2) and reaction-2 (S2->S3); modB owns reaction-3 (S3->S4).
    S3 is produced inside modA and consumed outside it -- the one genuine boundary species,
    correctly reported as an OUTPUT of modA. S1/S2/S4 are fully internal to one module or the
    other and must not appear."""
    candidates = real_boundary_derivation_modA["candidates"]
    assert candidates == [{"species_id": "compound-S3::in::compartment-1", "direction": "OUTPUT"}]


def test_real_boundary_derivation_is_symmetric_from_the_other_module(tmp_path):
    request_data = _base_request(
        "real-boundary-derivation-modB",
        attach_payload=_two_module_attach_payload(),
        module_id="modB",
    )
    try:
        returncode, result = _invoke(_ENTRYPOINT, tmp_path, request_data)
        assert returncode == 0, f"canonical entrypoint failed: {result}"
        assert result["candidates"] == [
            {"species_id": "compound-S3::in::compartment-1", "direction": "INPUT"}
        ]
    finally:
        _cleanup_run_artifacts("real-boundary-derivation-modB")


def test_real_boundary_derivation_is_idempotently_replayed(tmp_path):
    request_data = _base_request(
        "real-boundary-derivation-replay-test",
        attach_payload=_two_module_attach_payload(),
        module_id="modA",
    )
    try:
        returncode1, result1 = _invoke(_ENTRYPOINT, tmp_path, request_data)
        assert returncode1 == 0
        assert result1["replayed"] is False

        returncode2, result2 = _invoke(_ENTRYPOINT, tmp_path, request_data)
        assert returncode2 == 0
        assert result2["replayed"] is True
        assert result2["candidates"] == result1["candidates"]
    finally:
        _cleanup_run_artifacts("real-boundary-derivation-replay-test")
