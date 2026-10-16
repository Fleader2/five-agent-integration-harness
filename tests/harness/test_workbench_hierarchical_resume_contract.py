"""Tests for the Workbench <-> Harness hierarchical-recursion *resume* contract
(human-review/resume increment) and its canonical entrypoint
(``scripts/run_workbench_hierarchical_resume_request.py``).

Mirrors ``tests/harness/test_workbench_hierarchical_contracts.py``'s own established
convention exactly: one real, end-to-end subprocess invocation runs once per test session
(module-scoped fixture, chained off a real initial-invocation pause), and every other test
either asserts against that shared result or exercises a pre-execution rejection path directly
(fast, no subprocess, no agent invoked).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.harness.workbench_contracts import (
    WORKBENCH_HIERARCHICAL_CONTRACT_VERSION,
    WORKBENCH_HIERARCHICAL_RESUME_CONTRACT_VERSION,
    WorkbenchHierarchicalResumeRequest,
    WorkbenchHierarchicalRunResult,
    WorkbenchHierarchyNodeSummary,
    WorkbenchRunErrorCode,
    WorkbenchRunStatus,
    hierarchical_result_from_dict,
    hierarchical_result_to_dict,
    hierarchical_resume_request_from_dict,
    hierarchical_resume_request_to_dict,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_FIXTURES = _REPO_ROOT / "tests" / "fixtures"
_INITIAL_ENTRYPOINT = _REPO_ROOT / "scripts" / "run_workbench_hierarchical_request.py"
_RESUME_ENTRYPOINT = _REPO_ROOT / "scripts" / "run_workbench_hierarchical_resume_request.py"


def _base_initial_request(run_id: str, **overrides) -> dict:
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
            "require_human_review": True,
            "policy_version": "test-v1",
        },
        "input_artifact_references": {
            "stage1_synthetic_source": str(_FIXTURES / "synthetic_agent1_view.json"),
        },
        "exclude_single_module_from_ranking": False,
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


def test_resume_request_round_trips_through_dict():
    request = WorkbenchHierarchicalResumeRequest(
        contract_version=WORKBENCH_HIERARCHICAL_RESUME_CONTRACT_VERSION,
        run_id="resume-roundtrip",
        checkpoint={"checkpoint_version": "x", "nested": {"a": 1}},
        decisions={"pending-1": "APPROVE", "pending-2": "REJECT"},
        correlation_id="corr-1",
        notes="test",
        submitted_at="2026-01-01T00:00:00+00:00",
    )
    restored = hierarchical_resume_request_from_dict(hierarchical_resume_request_to_dict(request))
    assert restored == request


def test_resume_request_from_dict_raises_on_missing_required_field():
    data = {
        "contract_version": WORKBENCH_HIERARCHICAL_RESUME_CONTRACT_VERSION,
        "run_id": "missing-field",
        "decisions": {},
    }
    with pytest.raises(KeyError):
        hierarchical_resume_request_from_dict(data)


def test_result_with_checkpoint_round_trips_through_dict():
    result = WorkbenchHierarchicalRunResult(
        contract_version=WORKBENCH_HIERARCHICAL_RESUME_CONTRACT_VERSION,
        run_id="result-with-checkpoint",
        status=WorkbenchRunStatus.SUCCEEDED,
        root_model_id="m1",
        nodes=(
            WorkbenchHierarchyNodeSummary(
                node_id="node::depth0::root::000000",
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
                branch_stopping_reason="HUMAN_REVIEW_GATE",
                recursive_search_stopping_reason="MAX_ROUNDS",
                recursive_search_rounds=1,
                recursive_search_policy_version="test-v1",
            ),
        ),
        total_nodes_created=1,
        total_functional_evaluations_used=0,
        total_calibration_runs_used=1,
        requires_user_review=True,
        pending_review_modules=({"pending_id": "p1", "module_id": "modA"},),
        recursion_policy_version="hierarchical-recursion-v1",
        started_at="2026-01-01T00:00:00+00:00",
        completed_at="2026-01-01T00:00:10+00:00",
        error=None,
        summary="paused",
        checkpoint={"checkpoint_version": "hierarchical-recursion-checkpoint-v1", "x": [1, 2]},
    )
    restored = hierarchical_result_from_dict(hierarchical_result_to_dict(result))
    assert restored == result
    assert restored.checkpoint == {
        "checkpoint_version": "hierarchical-recursion-checkpoint-v1",
        "x": [1, 2],
    }


# --- Pre-execution rejections (fast, no subprocess) -----------------------------------------


def test_resume_contract_version_mismatch_is_rejected(tmp_path):
    request_data = {
        "contract_version": "not-the-real-version",
        "run_id": "resume-version-mismatch",
        "checkpoint": {},
        "decisions": {},
    }
    returncode, result = _invoke(_RESUME_ENTRYPOINT, tmp_path, request_data)
    try:
        assert returncode == 1
        assert result["status"] == WorkbenchRunStatus.FAILED.value
        assert result["error"]["code"] == WorkbenchRunErrorCode.CONTRACT_VERSION_MISMATCH.value
    finally:
        _cleanup_run_artifacts("resume-version-mismatch")


def test_resume_malformed_checkpoint_is_rejected_cleanly(tmp_path):
    request_data = {
        "contract_version": WORKBENCH_HIERARCHICAL_RESUME_CONTRACT_VERSION,
        "run_id": "resume-malformed-checkpoint",
        "checkpoint": {"this": "is not a real checkpoint"},
        "decisions": {},
    }
    returncode, result = _invoke(_RESUME_ENTRYPOINT, tmp_path, request_data)
    try:
        assert returncode == 1
        assert result["error"]["code"] == WorkbenchRunErrorCode.CHECKPOINT_REJECTED.value
    finally:
        _cleanup_run_artifacts("resume-malformed-checkpoint")


def test_resume_missing_request_field_is_rejected_cleanly(tmp_path):
    request_data = {
        "contract_version": WORKBENCH_HIERARCHICAL_RESUME_CONTRACT_VERSION,
        "run_id": "resume-missing-field",
        "decisions": {},
    }
    returncode, result = _invoke(_RESUME_ENTRYPOINT, tmp_path, request_data)
    try:
        assert returncode == 1
        assert result["error"]["code"] == WorkbenchRunErrorCode.MALFORMED_REQUEST.value
    finally:
        _cleanup_run_artifacts("resume-missing-field")


# --- Real, end-to-end subprocess invocation (module-scoped, runs once) ----------------------


@pytest.fixture(scope="module")
def real_paused_run(tmp_path_factory) -> dict:
    tmp_path = tmp_path_factory.mktemp("hierarchical-resume-real-initial")
    request_data = _base_initial_request("real-resume-contract-initial")
    returncode, result = _invoke(_INITIAL_ENTRYPOINT, tmp_path, request_data)
    assert returncode == 0, f"initial canonical entrypoint failed: {result}"
    assert result["requires_user_review"] is True, f"expected a real pause: {result}"
    assert result["checkpoint"] is not None
    yield result
    _cleanup_run_artifacts("real-resume-contract-initial")


@pytest.fixture(scope="module")
def real_resumed_run(real_paused_run, tmp_path_factory) -> dict:
    tmp_path = tmp_path_factory.mktemp("hierarchical-resume-real-resume")
    pending = real_paused_run["pending_review_modules"]
    decisions = {
        m["pending_id"]: ("APPROVE" if i == 0 else "REJECT") for i, m in enumerate(pending)
    }
    resume_request = {
        "contract_version": WORKBENCH_HIERARCHICAL_RESUME_CONTRACT_VERSION,
        "run_id": "real-resume-contract-resume-1",
        "checkpoint": real_paused_run["checkpoint"],
        "decisions": decisions,
    }
    returncode, result = _invoke(_RESUME_ENTRYPOINT, tmp_path, resume_request)
    assert returncode == 0, f"resume canonical entrypoint failed: {result}"
    yield result
    _cleanup_run_artifacts("real-resume-contract-resume-1")


def test_real_resume_succeeds(real_resumed_run):
    assert real_resumed_run["status"] == WorkbenchRunStatus.SUCCEEDED.value
    assert real_resumed_run["total_nodes_created"] >= 2


def test_real_resume_root_node_is_carried_through_unchanged(real_paused_run, real_resumed_run):
    root_before = next(n for n in real_paused_run["nodes"] if n["depth"] == 0)
    root_after = next(n for n in real_resumed_run["nodes"] if n["depth"] == 0)
    assert root_after == root_before


def test_real_resume_is_idempotently_replayed(real_paused_run, tmp_path):
    pending = real_paused_run["pending_review_modules"]
    decisions = {m["pending_id"]: "REJECT" for m in pending}
    resume_request = {
        "contract_version": WORKBENCH_HIERARCHICAL_RESUME_CONTRACT_VERSION,
        "run_id": "real-resume-contract-replay-test",
        "checkpoint": real_paused_run["checkpoint"],
        "decisions": decisions,
    }
    try:
        returncode1, result1 = _invoke(_RESUME_ENTRYPOINT, tmp_path, resume_request)
        assert returncode1 == 0
        assert result1["replayed"] is False

        returncode2, result2 = _invoke(_RESUME_ENTRYPOINT, tmp_path, resume_request)
        assert returncode2 == 0
        assert result2["replayed"] is True
        assert result2["total_nodes_created"] == result1["total_nodes_created"]
    finally:
        _cleanup_run_artifacts("real-resume-contract-replay-test")
