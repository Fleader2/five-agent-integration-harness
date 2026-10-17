"""Tests for the Workbench <-> Harness module-simulation contract (Executable-Module
Materialization increment) and its canonical entrypoint
(``scripts/run_workbench_module_simulation_request.py``).

Mirrors ``tests/harness/test_workbench_hierarchical_contracts.py``'s own established
convention: real, end-to-end subprocess invocations run against the repository's own synthetic
fixture; every pre-execution rejection path is exercised directly (fast, no subprocess, no
agent invoked).

**Boundary treatment is deliberately hand-supplied in these tests' own ``attach_payload``
fixtures.** Agent 2's own ``generate_module_artifacts`` never fabricates a boundary condition
(see ``app/harness/runners/run_agent2_materialize_module_handoff.py``'s own module docstring) --
a module reached purely through the hierarchical-recursion search's own ``attach_payload`` (no
explicit ``module_ports``) is honestly, correctly ``VIEW_ONLY`` (not yet simulatable), which
``test_real_run_rejects_a_module_with_no_boundary_treatment_cleanly`` below confirms directly
against a real hierarchical-recursion result. The *happy-path* real test instead supplies
``module_ports`` explicitly, standing in for whatever future caller (a human reviewer, or a
later Agent4/5 increment) would supply that boundary knowledge.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.harness.workbench_contracts import (
    WORKBENCH_MODULE_SIMULATION_CONTRACT_VERSION,
    WorkbenchModuleSimulationRequest,
    WorkbenchModuleSimulationResult,
    WorkbenchRunErrorCode,
    WorkbenchRunStatus,
    module_simulation_request_from_dict,
    module_simulation_request_to_dict,
    module_simulation_result_from_dict,
    module_simulation_result_to_dict,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_FIXTURES = _REPO_ROOT / "tests" / "fixtures"
_ENTRYPOINT = _REPO_ROOT / "scripts" / "run_workbench_module_simulation_request.py"
_HIERARCHICAL_ENTRYPOINT = _REPO_ROOT / "scripts" / "run_workbench_hierarchical_request.py"


def _clean_attach_payload() -> dict:
    """A hand-built, two-module split of the synthetic fixture's own three reactions, with
    explicit boundary-port treatment on every species -- the "happy path" scenario."""
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

    module_ports = [
        {
            "port_id": f"port::{mod}::{sid}",
            "module_id": mod,
            "species_id": sid,
            "direction": "INPUT",
            "externally_controlled": True,
            "initial_value": "1",
        }
        for mod in ("modA", "modB")
        for sid in species
    ]
    return {
        "modularization_id": modularization_id,
        "module_ids": ["modA", "modB"],
        "memberships": memberships,
        "module_ports": module_ports,
    }


def _base_request(run_id: str, *, attach_payload: dict, module_id: str, **overrides) -> dict:
    data = {
        "contract_version": WORKBENCH_MODULE_SIMULATION_CONTRACT_VERSION,
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
    request = WorkbenchModuleSimulationRequest(
        contract_version=WORKBENCH_MODULE_SIMULATION_CONTRACT_VERSION,
        run_id="roundtrip-test",
        project_id="proj-1",
        subproject_id="sub-1",
        attach_payload={"modularization_id": "x", "module_ids": ["modA"], "memberships": []},
        module_id="modA",
        agent1_organism_id="organism-1",
    )
    restored = module_simulation_request_from_dict(module_simulation_request_to_dict(request))
    assert restored == request


def test_request_from_dict_raises_on_missing_required_field():
    data = _base_request("missing-field-test", attach_payload={}, module_id="modA")
    del data["module_id"]
    with pytest.raises(KeyError):
        module_simulation_request_from_dict(data)


def test_result_round_trips_through_dict():
    result = WorkbenchModuleSimulationResult(
        contract_version=WORKBENCH_MODULE_SIMULATION_CONTRACT_VERSION,
        run_id="result-roundtrip",
        status=WorkbenchRunStatus.SUCCEEDED,
        module_id="modA",
        modularization_id="candidate::0001",
        module_handoff_summary={
            "model_id": "m1",
            "species_count": 2,
            "reaction_count": 1,
            "parameter_count": 1,
        },
        agent3_report={"report_id": "r1", "overall_status": "STEADY_STATE_FOUND"},
        started_at="2026-01-01T00:00:00+00:00",
        completed_at="2026-01-01T00:00:05+00:00",
        error=None,
        summary="simulated",
        warnings=("a warning",),
    )
    restored = module_simulation_result_from_dict(module_simulation_result_to_dict(result))
    assert restored == result


# --- Pre-execution rejections (fast, no subprocess) -----------------------------------------


def test_contract_version_mismatch_is_rejected(tmp_path):
    request_data = _base_request(
        "version-mismatch", attach_payload={}, module_id="modA", contract_version="not-real"
    )
    returncode, result = _invoke(_ENTRYPOINT, tmp_path, request_data)
    try:
        assert returncode == 1
        assert result["status"] == WorkbenchRunStatus.FAILED.value
        assert result["error"]["code"] == WorkbenchRunErrorCode.CONTRACT_VERSION_MISMATCH.value
    finally:
        _cleanup_run_artifacts("version-mismatch")


def test_invalid_stage1_input_neither_set_is_rejected(tmp_path):
    request_data = _base_request("stage1-neither", attach_payload={}, module_id="modA")
    del request_data["input_artifact_references"]["stage1_synthetic_source"]
    returncode, result = _invoke(_ENTRYPOINT, tmp_path, request_data)
    try:
        assert returncode == 1
        assert result["error"]["code"] == WorkbenchRunErrorCode.INVALID_STAGE1_INPUT.value
    finally:
        _cleanup_run_artifacts("stage1-neither")


def test_missing_synthetic_source_artifact_is_rejected(tmp_path):
    request_data = _base_request(
        "missing-synthetic-source",
        attach_payload={},
        module_id="modA",
        input_artifact_references={"stage1_synthetic_source": str(tmp_path / "nope.json")},
    )
    returncode, result = _invoke(_ENTRYPOINT, tmp_path, request_data)
    try:
        assert returncode == 1
        assert result["error"]["code"] == WorkbenchRunErrorCode.MISSING_INPUT_ARTIFACT.value
    finally:
        _cleanup_run_artifacts("missing-synthetic-source")


def test_malformed_request_is_rejected_cleanly(tmp_path):
    request_data = _base_request("malformed", attach_payload={}, module_id="modA")
    del request_data["attach_payload"]
    returncode, result = _invoke(_ENTRYPOINT, tmp_path, request_data)
    try:
        assert returncode == 1
        assert result["error"]["code"] == WorkbenchRunErrorCode.MALFORMED_REQUEST.value
    finally:
        _cleanup_run_artifacts("malformed")


# --- Real, end-to-end subprocess invocation: happy path (hand-supplied boundary treatment) --


@pytest.fixture(scope="module")
def real_module_simulation_success() -> dict:
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        request_data = _base_request(
            "real-module-simulation-success",
            attach_payload=_clean_attach_payload(),
            module_id="modA",
        )
        returncode, result = _invoke(_ENTRYPOINT, Path(tmp), request_data)
        assert returncode == 0, f"canonical entrypoint failed: {result}"
        yield result
    _cleanup_run_artifacts("real-module-simulation-success")


def test_real_module_simulation_succeeds(real_module_simulation_success):
    assert real_module_simulation_success["status"] == WorkbenchRunStatus.SUCCEEDED.value
    assert real_module_simulation_success["agent3_report"] is not None


def test_real_module_simulation_executed_the_module_not_the_root(real_module_simulation_success):
    """The whole synthetic root model has 3 reactions/3 parameters/4 species; modA (one of two
    hand-split modules) has only 2 of each reaction/parameter -- confirming Agent 3 received
    the module's own scoped artifact, never the root's."""
    summary = real_module_simulation_success["module_handoff_summary"]
    assert summary["reaction_count"] == 2
    assert summary["parameter_count"] == 2
    assert "modA" in summary["model_id"]


def test_real_module_simulation_is_idempotently_replayed(tmp_path):
    request_data = _base_request(
        "real-module-simulation-replay-test",
        attach_payload=_clean_attach_payload(),
        module_id="modA",
    )
    try:
        returncode1, result1 = _invoke(_ENTRYPOINT, tmp_path, request_data)
        assert returncode1 == 0
        assert result1["replayed"] is False

        returncode2, result2 = _invoke(_ENTRYPOINT, tmp_path, request_data)
        assert returncode2 == 0
        assert result2["replayed"] is True
        assert result2["module_handoff_summary"] == result1["module_handoff_summary"]
    finally:
        _cleanup_run_artifacts("real-module-simulation-replay-test")


# --- Real, end-to-end subprocess invocation: a module with no boundary treatment ------------


@pytest.fixture(scope="module")
def real_hierarchical_node_without_boundary_treatment() -> dict:
    """A real hierarchical-recursion run's own accepted module, exactly as the search itself
    reports it -- never hand-augmented with boundary ports."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        request_data = {
            "contract_version": "workbench-hierarchical-v1",
            "run_id": "real-module-simulation-view-only-source",
            "project_id": "proj-test",
            "subproject_id": "sub-test",
            "criteria_weights": {
                "weights": [{"criterion": "TOPOLOGICAL_SEPARATION", "weight": "1"}],
                "policy_version": "test-v1",
            },
            "search_policy": {
                "max_iterations": 1,
                "max_candidates_per_iteration": 10,
                "beam_width": 5,
                "allowed_operations": ["SPLIT_MODULE", "MOVE_REACTION"],
                "policy_version": "test-v1",
            },
            "calibration_selection_policy": {
                "max_candidates_per_generation": 1,
                "max_modules_per_candidate": None,
                "score_threshold": None,
                "rank_threshold": None,
                "only_if_could_change_ordering": False,
                "total_calibration_run_budget": 10,
                "policy_version": "test-v1",
            },
            "flat_orchestration_policy": {
                "max_rounds": 1,
                "max_total_candidates": 100,
                "improvement_epsilon": "0",
                "require_human_review": False,
                "policy_version": "test-v1",
            },
            "recursion_policy": {
                "max_depth": 1,
                "min_reactions_per_module": 1,
                "max_total_hierarchy_nodes": 20,
                "max_total_functional_evaluation_budget": 0,
                "max_total_calibration_budget": 10,
                "min_improvement_to_accept_child": "0",
                "require_human_review": False,
                "policy_version": "test-v1",
            },
            "input_artifact_references": {
                "stage1_synthetic_source": str(_FIXTURES / "synthetic_agent1_view.json"),
            },
            "exclude_single_module_from_ranking": False,
        }
        returncode, result = _invoke(_HIERARCHICAL_ENTRYPOINT, Path(tmp), request_data)
        assert returncode == 0, f"hierarchical entrypoint failed: {result}"
    node_with_attach = next(
        n for n in result["nodes"] if n["depth"] == 1 and n.get("attach_payload")
    )
    yield node_with_attach
    _cleanup_run_artifacts("real-module-simulation-view-only-source")


def test_real_run_rejects_a_module_with_no_boundary_treatment_cleanly(
    real_hierarchical_node_without_boundary_treatment, tmp_path
):
    node = real_hierarchical_node_without_boundary_treatment
    request_data = _base_request(
        "real-module-simulation-view-only",
        attach_payload=node["attach_payload"],
        module_id=node["parent_module_id"],
    )
    try:
        returncode, result = _invoke(_ENTRYPOINT, tmp_path, request_data)
        assert returncode == 1
        assert result["status"] == WorkbenchRunStatus.FAILED.value
        assert result["error"]["code"] == WorkbenchRunErrorCode.MODULE_SIMULATION_FAILED.value
        assert "no eligible standalone artifact" in result["error"]["message"]
    finally:
        _cleanup_run_artifacts("real-module-simulation-view-only")
