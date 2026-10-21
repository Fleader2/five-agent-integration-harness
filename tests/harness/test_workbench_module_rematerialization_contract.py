"""Tests for the Workbench <-> Harness module-rematerialization contract (Module-Set
Edited-Module Materialization increment) and its canonical entrypoint
(``scripts/run_workbench_module_rematerialization_request.py``).

Mirrors ``tests/harness/test_workbench_module_boundary_derivation_contract.py``'s own
established convention: real, end-to-end subprocess invocations run against the repository's
own synthetic fixture; every pre-execution rejection path is exercised directly (fast, no
subprocess, no agent invoked).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.harness.workbench_contracts import (
    WORKBENCH_MODULE_REMATERIALIZATION_CONTRACT_VERSION,
    WorkbenchModuleRematerializationRequest,
    WorkbenchModuleRematerializationResult,
    WorkbenchRunErrorCode,
    WorkbenchRunStatus,
    module_rematerialization_request_from_dict,
    module_rematerialization_request_to_dict,
    module_rematerialization_result_from_dict,
    module_rematerialization_result_to_dict,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_FIXTURES = _REPO_ROOT / "tests" / "fixtures"
_ENTRYPOINT = _REPO_ROOT / "scripts" / "run_workbench_module_rematerialization_request.py"

#: The synthetic fixture's own three reactions (reaction-1, reaction-2, reaction-3), each with
#: its own kinetic-law parameter and its own participant species -- the identical network
#: ``test_workbench_module_boundary_derivation_contract.py`` already relies on.
_ALL_REACTIONS = ("reaction-1", "reaction-2", "reaction-3")


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
        "contract_version": WORKBENCH_MODULE_REMATERIALIZATION_CONTRACT_VERSION,
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
    request = WorkbenchModuleRematerializationRequest(
        contract_version=WORKBENCH_MODULE_REMATERIALIZATION_CONTRACT_VERSION,
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
        agent1_organism_id="organism-1",
    )
    restored = module_rematerialization_request_from_dict(
        module_rematerialization_request_to_dict(request)
    )
    assert restored == request


def test_request_from_dict_raises_on_missing_required_field():
    data = _base_request("missing-field-test", attach_payload={}, module_id="modA")
    del data["module_id"]
    with pytest.raises(KeyError):
        module_rematerialization_request_from_dict(data)


def test_result_round_trips_through_dict():
    result = WorkbenchModuleRematerializationResult(
        contract_version=WORKBENCH_MODULE_REMATERIALIZATION_CONTRACT_VERSION,
        run_id="result-roundtrip",
        status=WorkbenchRunStatus.SUCCEEDED,
        module_id="modA",
        module_handoff={"species": [], "reactions": [], "parameters": []},
        readiness_blocked_reason=None,
        lineage={"retained_reaction_ids": ["reaction-1"]},
        unresolved_dependencies=(),
        started_at="2026-01-01T00:00:00+00:00",
        completed_at="2026-01-01T00:00:05+00:00",
        error=None,
        summary="rematerialized",
        warnings=("a warning",),
    )
    restored = module_rematerialization_result_from_dict(
        module_rematerialization_result_to_dict(result)
    )
    assert restored == result


# --- Pre-execution rejections (fast, no subprocess) -----------------------------------------


def test_contract_version_mismatch_is_rejected(tmp_path):
    request_data = _base_request(
        "remat-version-mismatch", attach_payload={}, module_id="modA", contract_version="not-real"
    )
    returncode, result = _invoke(_ENTRYPOINT, tmp_path, request_data)
    try:
        assert returncode == 1
        assert result["status"] == WorkbenchRunStatus.FAILED.value
        assert result["error"]["code"] == WorkbenchRunErrorCode.CONTRACT_VERSION_MISMATCH.value
    finally:
        _cleanup_run_artifacts("remat-version-mismatch")


def test_invalid_stage1_input_neither_set_is_rejected(tmp_path):
    request_data = _base_request("remat-stage1-neither", attach_payload={}, module_id="modA")
    del request_data["input_artifact_references"]["stage1_synthetic_source"]
    returncode, result = _invoke(_ENTRYPOINT, tmp_path, request_data)
    try:
        assert returncode == 1
        assert result["error"]["code"] == WorkbenchRunErrorCode.INVALID_STAGE1_INPUT.value
    finally:
        _cleanup_run_artifacts("remat-stage1-neither")


def test_missing_synthetic_source_artifact_is_rejected(tmp_path):
    """ "Missing source content" (task instructions, Phase A verification): a
    ``stage1_synthetic_source`` path that does not exist on disk is rejected before any Agent 2
    subprocess is ever started -- never silently reconstructed from the request's own
    (necessarily incomplete) membership summary."""
    request_data = _base_request(
        "remat-missing-synthetic-source",
        attach_payload={},
        module_id="modA",
        input_artifact_references={"stage1_synthetic_source": str(tmp_path / "nope.json")},
    )
    returncode, result = _invoke(_ENTRYPOINT, tmp_path, request_data)
    try:
        assert returncode == 1
        assert result["error"]["code"] == WorkbenchRunErrorCode.MISSING_INPUT_ARTIFACT.value
    finally:
        _cleanup_run_artifacts("remat-missing-synthetic-source")


def test_malformed_request_is_rejected_cleanly(tmp_path):
    request_data = _base_request("remat-malformed", attach_payload={}, module_id="modA")
    del request_data["attach_payload"]
    returncode, result = _invoke(_ENTRYPOINT, tmp_path, request_data)
    try:
        assert returncode == 1
        assert result["error"]["code"] == WorkbenchRunErrorCode.MALFORMED_REQUEST.value
    finally:
        _cleanup_run_artifacts("remat-malformed")


# --- Real, end-to-end subprocess invocation -------------------------------------------------


def test_rematerializing_the_original_full_selection_matches_legacy_behavior(tmp_path):
    """The exact, unedited selection every other module-scoped contract already handles
    (all three reactions as one module) must still rebuild a complete, correct closure --
    proof that inserting materialize_submodel did not change legacy behavior."""
    run_id = "remat-legacy-unedited"
    try:
        request_data = _base_request(
            run_id,
            attach_payload=_reaction_only_attach("cand::legacy", "modAll", list(_ALL_REACTIONS)),
            module_id="modAll",
        )
        returncode, result = _invoke(_ENTRYPOINT, tmp_path, request_data)
        assert returncode == 0, f"canonical entrypoint failed: {result}"
        assert result["status"] == WorkbenchRunStatus.SUCCEEDED.value
        assert sorted(result["lineage"]["retained_reaction_ids"]) == sorted(_ALL_REACTIONS)
        # No boundary ports supplied -> materialized but not yet simulatable.
        assert result["module_handoff"] is None
        assert result["readiness_blocked_reason"] is not None
    finally:
        _cleanup_run_artifacts(run_id)


def test_moving_a_reaction_between_siblings_rebuilds_both_with_correct_closures(tmp_path):
    """reaction-1+reaction-2 vs. reaction-3 is the original split; moving reaction-2 onto
    reaction-3's own module must change which parameter/species each one's own rebuilt closure
    retains -- the central scientific claim this whole increment exists to prove."""
    run_id_a = "remat-edited-modA"
    run_id_b = "remat-edited-modB"
    try:
        request_a = _base_request(
            run_id_a,
            attach_payload=_reaction_only_attach("cand::edited", "modA", ["reaction-1"]),
            module_id="modA",
        )
        returncode_a, result_a = _invoke(_ENTRYPOINT, tmp_path, request_a)
        assert returncode_a == 0, f"canonical entrypoint failed: {result_a}"
        assert result_a["lineage"]["retained_reaction_ids"] == ["reaction-1"]
        assert "k_reaction-1_protein-1" in result_a["lineage"]["retained_parameter_ids"]
        assert "k_reaction-2_protein-2" not in result_a["lineage"]["retained_parameter_ids"]

        request_b = _base_request(
            run_id_b,
            attach_payload=_reaction_only_attach(
                "cand::edited", "modB", ["reaction-2", "reaction-3"]
            ),
            module_id="modB",
        )
        returncode_b, result_b = _invoke(_ENTRYPOINT, tmp_path, request_b)
        assert returncode_b == 0, f"canonical entrypoint failed: {result_b}"
        assert sorted(result_b["lineage"]["retained_reaction_ids"]) == ["reaction-2", "reaction-3"]
        assert "k_reaction-2_protein-2" in result_b["lineage"]["retained_parameter_ids"]
        assert "k_reaction-1_protein-1" not in result_b["lineage"]["retained_parameter_ids"]
    finally:
        _cleanup_run_artifacts(run_id_a)
        _cleanup_run_artifacts(run_id_b)


def test_an_unknown_reaction_id_is_rejected_not_silently_dropped(tmp_path):
    run_id = "remat-unknown-reaction"
    try:
        request_data = _base_request(
            run_id,
            attach_payload=_reaction_only_attach(
                "cand::bad", "modX", ["reaction-1", "totally-invented-reaction"]
            ),
            module_id="modX",
        )
        returncode, result = _invoke(_ENTRYPOINT, tmp_path, request_data)
        assert returncode == 1
        assert result["status"] == WorkbenchRunStatus.FAILED.value
        assert (
            result["error"]["code"] == WorkbenchRunErrorCode.MODULE_REMATERIALIZATION_FAILED.value
        )
    finally:
        _cleanup_run_artifacts(run_id)


def test_supplying_resolved_boundary_ports_produces_an_executable_handoff(tmp_path):
    """modA = reaction-1+reaction-2 (produces compound-S3), modB = reaction-3 (consumes it) --
    the identical two-module split the boundary-derivation contract's own tests already use.
    Supplying modA's own resolved treatment for the one real crossing species must make it
    genuinely executable."""
    run_id = "remat-with-ports"
    try:
        request_data = _base_request(
            run_id,
            attach_payload=_reaction_only_attach(
                "cand::ports", "modA", ["reaction-1", "reaction-2"]
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
        returncode, result = _invoke(_ENTRYPOINT, tmp_path, request_data)
        assert returncode == 0, f"canonical entrypoint failed: {result}"
        assert result["module_handoff"] is not None
        assert result["readiness_blocked_reason"] is None
    finally:
        _cleanup_run_artifacts(run_id)


def test_real_rematerialization_is_idempotently_replayed(tmp_path):
    run_id = "remat-replay-test"
    try:
        request_data = _base_request(
            run_id,
            attach_payload=_reaction_only_attach("cand::replay", "modA", ["reaction-1"]),
            module_id="modA",
        )
        returncode1, result1 = _invoke(_ENTRYPOINT, tmp_path, request_data)
        assert returncode1 == 0
        assert result1["replayed"] is False

        returncode2, result2 = _invoke(_ENTRYPOINT, tmp_path, request_data)
        assert returncode2 == 0
        assert result2["replayed"] is True
        assert result2["lineage"] == result1["lineage"]
    finally:
        _cleanup_run_artifacts(run_id)
