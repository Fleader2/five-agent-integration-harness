"""Tests for the Workbench <-> Harness hierarchical-recursion invocation/result contract and
its canonical entrypoint (``scripts/run_workbench_hierarchical_request.py``).

Mirrors ``tests/harness/test_workbench_contracts.py``'s own established convention exactly: the
one real, end-to-end subprocess invocation of the canonical entrypoint runs **once** per test
session (module-scoped fixture); every other test either asserts against that one shared result
or exercises a pre-execution rejection path directly (fast, no subprocess, no agent invoked).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.harness.workbench_contracts import (
    WORKBENCH_HIERARCHICAL_CONTRACT_VERSION,
    WorkbenchHierarchicalRunResult,
    WorkbenchHierarchyNodeSummary,
    WorkbenchRunError,
    WorkbenchRunErrorCode,
    WorkbenchRunStatus,
    hierarchical_request_from_dict,
    hierarchical_result_from_dict,
    hierarchical_result_to_dict,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_FIXTURES = _REPO_ROOT / "tests" / "fixtures"
_ENTRYPOINT = _REPO_ROOT / "scripts" / "run_workbench_hierarchical_request.py"


def _base_request(run_id: str, **overrides) -> dict:
    data = {
        "contract_version": WORKBENCH_HIERARCHICAL_CONTRACT_VERSION,
        "run_id": run_id,
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
            "max_depth": 2,
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
    data.update(overrides)
    return data


def _invoke_entrypoint(tmp_path: Path, request_data: dict) -> tuple[int, dict]:
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
    data = _base_request("roundtrip-test", model_id="model-1")
    request = hierarchical_request_from_dict(data)
    assert request.run_id == "roundtrip-test"
    assert request.model_id == "model-1"
    assert request.recursion_policy["max_depth"] == 2


def test_request_from_dict_raises_on_missing_required_field():
    data = _base_request("missing-field-test")
    del data["recursion_policy"]
    with pytest.raises(KeyError):
        hierarchical_request_from_dict(data)


def test_result_round_trips_through_dict():
    result = WorkbenchHierarchicalRunResult(
        contract_version=WORKBENCH_HIERARCHICAL_CONTRACT_VERSION,
        run_id="result-roundtrip",
        status=WorkbenchRunStatus.SUCCEEDED,
        root_model_id="m1",
        nodes=(
            WorkbenchHierarchyNodeSummary(
                node_id="node::depth0::root::abc",
                depth=0,
                parent_modularization_id=None,
                parent_module_id=None,
                child_submodel_id="m1",
                child_modularization_id="cand-1",
                child_module_ids=("modA", "modB"),
                accepted=True,
                reason="accepted",
                baseline_score=None,
                child_score="0.5",
                branch_stopping_reason=None,
                recursive_search_stopping_reason="MAX_ROUNDS",
                recursive_search_rounds=1,
                recursive_search_policy_version="test-v1",
            ),
        ),
        total_nodes_created=1,
        total_functional_evaluations_used=0,
        total_calibration_runs_used=1,
        requires_user_review=False,
        pending_review_modules=(),
        recursion_policy_version="hierarchical-recursion-v1",
        started_at="2026-01-01T00:00:00+00:00",
        completed_at="2026-01-01T00:00:10+00:00",
        error=None,
        summary="1 node(s) explored",
        warnings=("a warning",),
    )
    restored = hierarchical_result_from_dict(hierarchical_result_to_dict(result))
    assert restored == result


def test_result_with_error_round_trips_through_dict():
    result = WorkbenchHierarchicalRunResult(
        contract_version=WORKBENCH_HIERARCHICAL_CONTRACT_VERSION,
        run_id="result-with-error",
        status=WorkbenchRunStatus.FAILED,
        root_model_id=None,
        nodes=(),
        total_nodes_created=0,
        total_functional_evaluations_used=0,
        total_calibration_runs_used=0,
        requires_user_review=False,
        pending_review_modules=(),
        recursion_policy_version="",
        started_at=None,
        completed_at=None,
        error=WorkbenchRunError(code="MALFORMED_REQUEST", message="broke"),
        summary="failed",
    )
    restored = hierarchical_result_from_dict(hierarchical_result_to_dict(result))
    assert restored == result


# --- Pre-execution rejections (fast, no subprocess) ------------------------------------------


def test_contract_version_mismatch_is_rejected(tmp_path):
    request_data = _base_request("version-mismatch", contract_version="not-the-real-version")
    returncode, result = _invoke_entrypoint(tmp_path, request_data)
    try:
        assert returncode == 1
        assert result["status"] == WorkbenchRunStatus.FAILED.value
        assert result["error"]["code"] == WorkbenchRunErrorCode.CONTRACT_VERSION_MISMATCH.value
    finally:
        _cleanup_run_artifacts("version-mismatch")


def test_invalid_stage1_input_both_set_is_rejected(tmp_path):
    request_data = _base_request("stage1-both", agent1_organism_id="some-organism-id")
    returncode, result = _invoke_entrypoint(tmp_path, request_data)
    try:
        assert returncode == 1
        assert result["error"]["code"] == WorkbenchRunErrorCode.INVALID_STAGE1_INPUT.value
    finally:
        _cleanup_run_artifacts("stage1-both")


def test_invalid_stage1_input_neither_set_is_rejected(tmp_path):
    request_data = _base_request("stage1-neither")
    del request_data["input_artifact_references"]["stage1_synthetic_source"]
    returncode, result = _invoke_entrypoint(tmp_path, request_data)
    try:
        assert returncode == 1
        assert result["error"]["code"] == WorkbenchRunErrorCode.INVALID_STAGE1_INPUT.value
    finally:
        _cleanup_run_artifacts("stage1-neither")


def test_missing_synthetic_source_artifact_is_rejected(tmp_path):
    request_data = _base_request(
        "missing-synthetic-source",
        input_artifact_references={
            "stage1_synthetic_source": str(tmp_path / "does-not-exist.json")
        },
    )
    returncode, result = _invoke_entrypoint(tmp_path, request_data)
    try:
        assert returncode == 1
        assert result["error"]["code"] == WorkbenchRunErrorCode.MISSING_INPUT_ARTIFACT.value
    finally:
        _cleanup_run_artifacts("missing-synthetic-source")


def test_malformed_nested_policy_is_rejected_cleanly(tmp_path):
    """A ``recursion_policy`` dict missing one of its own required nested keys is rejected as
    ``MALFORMED_REQUEST``, never an uncaught traceback."""
    request_data = _base_request("malformed-nested-policy")
    del request_data["recursion_policy"]["max_depth"]
    returncode, result = _invoke_entrypoint(tmp_path, request_data)
    try:
        assert returncode == 1
        assert result["error"]["code"] == WorkbenchRunErrorCode.MALFORMED_REQUEST.value
    finally:
        _cleanup_run_artifacts("malformed-nested-policy")


# --- Real, end-to-end subprocess invocation (module-scoped, runs once) ----------------------


@pytest.fixture(scope="module")
def real_hierarchical_run(tmp_path_factory) -> dict:
    tmp_path = tmp_path_factory.mktemp("hierarchical-real-run")
    request_data = _base_request("real-hierarchical-run-test")
    returncode, result = _invoke_entrypoint(tmp_path, request_data)
    assert returncode == 0, f"canonical entrypoint failed: {result}"
    yield result
    _cleanup_run_artifacts("real-hierarchical-run-test")


def test_real_run_succeeds_with_a_real_two_node_hierarchy(real_hierarchical_run):
    result = real_hierarchical_run
    assert result["status"] == WorkbenchRunStatus.SUCCEEDED.value
    assert result["root_model_id"]
    assert len(result["nodes"]) >= 1
    root = next(n for n in result["nodes"] if n["depth"] == 0)
    assert root["accepted"] is True


def test_real_run_reports_nonzero_total_nodes_created(real_hierarchical_run):
    assert real_hierarchical_run["total_nodes_created"] >= 1


def test_real_run_discloses_the_no_dataset_warning(real_hierarchical_run):
    assert any("NO_DATASET_AVAILABLE" in w for w in real_hierarchical_run["warnings"])


def test_real_run_is_idempotently_replayed(tmp_path):
    request_data = _base_request("real-hierarchical-replay-test")
    try:
        returncode1, result1 = _invoke_entrypoint(tmp_path, request_data)
        assert returncode1 == 0
        assert result1["replayed"] is False

        returncode2, result2 = _invoke_entrypoint(tmp_path, request_data)
        assert returncode2 == 0
        assert result2["replayed"] is True
        assert result2["root_model_id"] == result1["root_model_id"]
        assert result2["nodes"] == result1["nodes"]
    finally:
        _cleanup_run_artifacts("real-hierarchical-replay-test")
