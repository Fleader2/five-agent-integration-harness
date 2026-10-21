"""Tests for the Workbench <-> Harness module-set-simulation contract (Module-Set
Edited-Module Materialization increment, Phase B) and its canonical entrypoint
(``scripts/run_workbench_module_set_simulation_request.py``).

Mirrors ``tests/harness/test_workbench_module_simulation_contract.py``'s own established
convention: real, end-to-end subprocess invocations (two real rounds -- Agent 2 then Agent 3)
run against the repository's own synthetic fixture.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.harness.workbench_contracts import (
    WORKBENCH_MODULE_SET_SIMULATION_CONTRACT_VERSION,
    WorkbenchModuleSetSimulationRequest,
    WorkbenchModuleSetSimulationResult,
    WorkbenchRunErrorCode,
    WorkbenchRunStatus,
    module_set_simulation_request_from_dict,
    module_set_simulation_request_to_dict,
    module_set_simulation_result_from_dict,
    module_set_simulation_result_to_dict,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_FIXTURES = _REPO_ROOT / "tests" / "fixtures"
_ENTRYPOINT = _REPO_ROOT / "scripts" / "run_workbench_module_set_simulation_request.py"


def _reaction_only_attach(modularization_id: str, module_id: str, reaction_ids: list[str]) -> dict:
    return {
        "modularization_id": modularization_id,
        "module_ids": [module_id],
        "memberships": [
            {"module_id": module_id, "component_type": "REACTION", "component_id": rid}
            for rid in reaction_ids
        ],
    }


def _base_request(run_id: str, *, attach_payload: dict, module_id: str, **overrides) -> dict:
    data = {
        "contract_version": WORKBENCH_MODULE_SET_SIMULATION_CONTRACT_VERSION,
        "run_id": run_id,
        "project_id": "proj-test",
        "subproject_id": "sub-test",
        "attach_payload": attach_payload,
        "module_id": module_id,
        "module_ports": [],
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
    request = WorkbenchModuleSetSimulationRequest(
        contract_version=WORKBENCH_MODULE_SET_SIMULATION_CONTRACT_VERSION,
        run_id="roundtrip-test",
        project_id="proj-1",
        subproject_id="sub-1",
        attach_payload={"modularization_id": "x", "module_ids": ["modA"], "memberships": []},
        module_id="modA",
        module_ports=(
            {
                "port_id": "p1",
                "module_id": "modA",
                "species_id": "s1",
                "direction": "OUTPUT",
                "externally_controlled": True,
            },
        ),
    )
    restored = module_set_simulation_request_from_dict(
        module_set_simulation_request_to_dict(request)
    )
    assert restored == request


def test_result_round_trips_through_dict():
    result = WorkbenchModuleSetSimulationResult(
        contract_version=WORKBENCH_MODULE_SET_SIMULATION_CONTRACT_VERSION,
        run_id="result-roundtrip",
        status=WorkbenchRunStatus.SUCCEEDED,
        module_id="modA",
        module_handoff_summary={"species_count": 2},
        lineage={"retained_reaction_ids": ["reaction-1"]},
        agent3_report={"overall_status": "SUCCESS"},
        started_at="2026-01-01T00:00:00+00:00",
        completed_at="2026-01-01T00:00:05+00:00",
        error=None,
        summary="simulated",
    )
    restored = module_set_simulation_result_from_dict(module_set_simulation_result_to_dict(result))
    assert restored == result


# --- Pre-execution rejections (fast, no subprocess) -----------------------------------------


def test_contract_version_mismatch_is_rejected(tmp_path):
    request_data = _base_request(
        "setsim-version-mismatch", attach_payload={}, module_id="modA", contract_version="not-real"
    )
    returncode, result = _invoke(_ENTRYPOINT, tmp_path, request_data)
    try:
        assert returncode == 1
        assert result["error"]["code"] == WorkbenchRunErrorCode.CONTRACT_VERSION_MISMATCH.value
    finally:
        _cleanup_run_artifacts("setsim-version-mismatch")


def test_missing_boundary_treatments_is_rejected_not_materialize_only(tmp_path):
    """This contract's entire purpose is simulation -- never a quiet materialize-only
    fallback when no boundary treatments were supplied."""
    run_id = "setsim-no-ports"
    try:
        request_data = _base_request(
            run_id,
            attach_payload=_reaction_only_attach("cand::noports", "modA", ["reaction-1"]),
            module_id="modA",
        )
        returncode, result = _invoke(_ENTRYPOINT, tmp_path, request_data)
        assert returncode == 1
        assert result["error"]["code"] == WorkbenchRunErrorCode.MODULE_SET_SIMULATION_FAILED.value
        assert result["agent3_report"] is None
    finally:
        _cleanup_run_artifacts(run_id)


# --- Real, end-to-end subprocess invocation (Agent 2 rebuild + real Agent 3) -----------------


@pytest.fixture(scope="module")
def real_edited_module_simulation() -> dict:
    """modA = reaction-1+reaction-2 (produces compound-S3), with modA's own resolved boundary
    treatment for the one real crossing species -- a genuine, edited (two-of-three-reaction)
    selection, simulated for real through both Agent 2 and Agent 3."""
    import tempfile

    run_id = "setsim-real-edited"
    with tempfile.TemporaryDirectory() as tmp:
        request_data = _base_request(
            run_id,
            attach_payload=_reaction_only_attach(
                "cand::setsim", "modA", ["reaction-1", "reaction-2"]
            ),
            module_id="modA",
            module_ports=[
                {
                    "port_id": "port::modA::compound-S3",
                    "module_id": "modA",
                    "species_id": "compound-S3::in::compartment-1",
                    "direction": "OUTPUT",
                    "externally_controlled": True,
                    "initial_value": "1.0",
                    "unit": "mM",
                }
            ],
        )
        returncode, result = _invoke(_ENTRYPOINT, Path(tmp), request_data)
        assert returncode == 0, f"canonical entrypoint failed: {result}"
        yield result
    _cleanup_run_artifacts(run_id)


def test_real_edited_module_simulation_succeeds(real_edited_module_simulation):
    assert real_edited_module_simulation["status"] == WorkbenchRunStatus.SUCCEEDED.value


def test_real_edited_module_simulation_has_a_real_agent3_report(real_edited_module_simulation):
    report = real_edited_module_simulation["agent3_report"]
    assert report is not None
    assert "overall_status" in report


def test_real_edited_module_simulation_handoff_reflects_only_the_selected_reactions(
    real_edited_module_simulation,
):
    """The central cross-cutting proof: the executable artifact Agent 3 actually simulated
    reflects exactly the edited two-reaction selection, not the original three-reaction
    module and not a third, unrelated reaction's own species/parameters."""
    summary = real_edited_module_simulation["module_handoff_summary"]
    assert summary["reaction_count"] == 2
    lineage = real_edited_module_simulation["lineage"]
    assert sorted(lineage["retained_reaction_ids"]) == ["reaction-1", "reaction-2"]
    assert "k_reaction-3_protein-3" not in lineage["retained_parameter_ids"]
