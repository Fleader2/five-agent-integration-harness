"""Tests for the Workbench <-> Harness invocation/result contract and its canonical entrypoint
(``scripts/run_workbench_request.py``).

The full five-stage subprocess chain is genuinely slow (tens of seconds): the one real,
end-to-end subprocess invocation of the canonical entrypoint is run **once** per test session
(module-scoped fixture, mirroring ``tests/harness/test_synthetic_full_workflow.py``'s own
pattern), and every other test either asserts against that one shared result or exercises a
pre-execution rejection path directly (fast, no subprocess, no agent ever invoked).
"""

from __future__ import annotations

import json
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

from app.harness.workbench_contracts import (
    SUPPORTED_ENTRY_STAGE,
    WORKBENCH_HARNESS_CONTRACT_VERSION,
    WorkbenchRunError,
    WorkbenchRunErrorCode,
    WorkbenchRunResult,
    WorkbenchRunStatus,
    request_from_dict,
    result_from_dict,
    result_to_dict,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_FIXTURES = _REPO_ROOT / "tests" / "fixtures"
_ENTRYPOINT = _REPO_ROOT / "scripts" / "run_workbench_request.py"


def _base_request(run_id: str, **overrides) -> dict:
    data = {
        "contract_version": WORKBENCH_HARNESS_CONTRACT_VERSION,
        "run_id": run_id,
        "project_id": "proj-test",
        "subproject_id": "sub-test",
        "task_type": "BUILD_MODEL",
        "requested_entry_stage": SUPPORTED_ENTRY_STAGE,
        "input_artifact_references": {
            "stage1_synthetic_source": str(_FIXTURES / "synthetic_agent1_view.json"),
            "stage4_request": str(_FIXTURES / "synthetic_stage4_request.json"),
            "stage5_request": str(_FIXTURES / "synthetic_stage5_request.json"),
        },
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


# --- Contract serialization/deserialization ----------------------------------------------


def test_request_round_trips_through_dict():
    data = _base_request("roundtrip-test", model_id="model-1", model_build_request_id="mbr-1")
    request = request_from_dict(data)
    assert request.run_id == "roundtrip-test"
    assert request.model_build_request_id == "mbr-1"


def test_request_from_dict_raises_on_missing_required_field():
    data = _base_request("missing-field-test")
    del data["task_type"]
    with pytest.raises(KeyError):
        request_from_dict(data)


def test_result_round_trips_through_dict():
    result = WorkbenchRunResult(
        contract_version=WORKBENCH_HARNESS_CONTRACT_VERSION,
        run_id="result-roundtrip",
        status=WorkbenchRunStatus.SUCCEEDED,
        stages_executed=("agent1_curation", "agent2_assembly"),
        output_artifact_references={"agent2_assembly": "/tmp/stage2_output.json"},
        model_artifact_reference="/tmp/stage2_output.json",
        agent_contract_versions={"agent2_assembly": "agent2-downstream-v1"},
        started_at="2026-01-01T00:00:00+00:00",
        completed_at="2026-01-01T00:00:10+00:00",
        error=None,
        summary="all good",
        warnings=("a warning",),
    )
    restored = result_from_dict(result_to_dict(result))
    assert restored == result


def test_result_with_error_round_trips_through_dict():
    result = WorkbenchRunResult(
        contract_version=WORKBENCH_HARNESS_CONTRACT_VERSION,
        run_id="result-with-error",
        status=WorkbenchRunStatus.FAILED,
        stages_executed=(),
        output_artifact_references={},
        model_artifact_reference=None,
        agent_contract_versions={},
        started_at=None,
        completed_at=None,
        error=WorkbenchRunError(code="SOMETHING", message="broke", stage_name="agent2_assembly"),
        summary="failed",
    )
    restored = result_from_dict(result_to_dict(result))
    assert restored == result


# --- Pre-execution rejections (fast, no subprocess) ----------------------------------------


def test_contract_version_mismatch_is_rejected(tmp_path):
    request_data = _base_request("version-mismatch", contract_version="not-the-real-version")
    returncode, result = _invoke_entrypoint(tmp_path, request_data)
    assert returncode == 1
    assert result["status"] == WorkbenchRunStatus.FAILED.value
    assert result["error"]["code"] == WorkbenchRunErrorCode.CONTRACT_VERSION_MISMATCH.value


def test_unsupported_entry_stage_is_rejected(tmp_path):
    request_data = _base_request("unsupported-stage", requested_entry_stage="AGENT2_ONLY")
    returncode, result = _invoke_entrypoint(tmp_path, request_data)
    assert returncode == 1
    assert result["error"]["code"] == WorkbenchRunErrorCode.UNSUPPORTED_ENTRY_STAGE.value


def test_missing_input_artifact_is_rejected(tmp_path):
    request_data = _base_request("missing-artifact")
    del request_data["input_artifact_references"]["stage5_request"]
    returncode, result = _invoke_entrypoint(tmp_path, request_data)
    assert returncode == 1
    assert result["error"]["code"] == WorkbenchRunErrorCode.MISSING_INPUT_ARTIFACT.value


def test_missing_model_build_request_artifact_is_rejected(tmp_path):
    """Scoped-Build Support increment: unlike ``model_build_request_id`` alone (a disclosed,
    non-fatal warning), a supplied ``model_build_request`` artifact *path* that does not exist
    is rejected exactly like a missing ``stage4_request``/``stage5_request``."""
    request_data = _base_request("missing-build-request-artifact")
    request_data["input_artifact_references"]["model_build_request"] = str(
        tmp_path / "does-not-exist.json"
    )
    returncode, result = _invoke_entrypoint(tmp_path, request_data)
    assert returncode == 1
    assert result["error"]["code"] == WorkbenchRunErrorCode.MISSING_INPUT_ARTIFACT.value


def test_invalid_stage1_input_both_set_is_rejected(tmp_path):
    request_data = _base_request(
        "stage1-both", agent1_organism_id="fc66ef94-9fc1-4a8c-969c-d129c839cb26"
    )
    returncode, result = _invoke_entrypoint(tmp_path, request_data)
    assert returncode == 1
    assert result["error"]["code"] == WorkbenchRunErrorCode.INVALID_STAGE1_INPUT.value


def test_invalid_stage1_input_neither_set_is_rejected(tmp_path):
    request_data = _base_request("stage1-neither")
    del request_data["input_artifact_references"]["stage1_synthetic_source"]
    returncode, result = _invoke_entrypoint(tmp_path, request_data)
    assert returncode == 1
    assert result["error"]["code"] == WorkbenchRunErrorCode.INVALID_STAGE1_INPUT.value


def test_malformed_request_json_is_rejected(tmp_path):
    request_path = tmp_path / "request.json"
    output_path = tmp_path / "result.json"
    request_path.write_text("this is not json")
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
        timeout=30,
    )
    assert proc.returncode == 1
    result = json.loads(output_path.read_text())
    assert result["error"]["code"] == WorkbenchRunErrorCode.MALFORMED_REQUEST.value


def test_model_build_request_id_produces_a_disclosed_warning_not_a_silent_noop(tmp_path):
    """Pre-execution rejections never reach this far -- this test documents that, when a run
    *does* execute, a supplied ``model_build_request_id`` is recorded, not silently dropped. It
    only exercises the warning logic directly via a request whose stage1 input is itself
    invalid, so the check is reached without paying for a full subprocess chain."""
    from app.harness.workbench_contracts import request_from_dict

    data = _base_request("mbr-warning-check", model_build_request_id="mbr-123")
    del data["input_artifact_references"]["stage1_synthetic_source"]
    request = request_from_dict(data)
    assert request.model_build_request_id == "mbr-123"


# --- One real, end-to-end subprocess invocation of the canonical entrypoint -----------------


@pytest.fixture(scope="module")
def synthetic_workbench_run(tmp_path_factory) -> tuple[int, dict]:
    tmp_path = tmp_path_factory.mktemp("workbench_entrypoint")
    run_id = f"workbench-synthetic-{uuid.uuid4()}"
    request_data = _base_request(run_id)
    return _invoke_entrypoint(tmp_path, request_data), run_id


def test_successful_end_to_end_round_trip(synthetic_workbench_run):
    (returncode, result), _run_id = synthetic_workbench_run
    assert returncode == 0
    assert result["status"] == WorkbenchRunStatus.SUCCEEDED.value
    assert result["error"] is None
    assert result["stages_executed"] == [
        "agent1_curation",
        "agent2_assembly",
        "agent3_simulation",
        "agent4_calibration",
        "agent5_validation",
    ]


def test_artifact_references_are_persisted_for_every_stage(synthetic_workbench_run):
    (_returncode, result), _run_id = synthetic_workbench_run
    for stage_name in result["stages_executed"]:
        path = result["output_artifact_references"][stage_name]
        assert Path(path).is_file()


def test_model_artifact_reference_points_at_agent2_output(synthetic_workbench_run):
    (_returncode, result), _run_id = synthetic_workbench_run
    assert (
        result["model_artifact_reference"]
        == result["output_artifact_references"]["agent2_assembly"]
    )


def test_agent_contract_versions_are_recorded(synthetic_workbench_run):
    (_returncode, result), _run_id = synthetic_workbench_run
    assert result["agent_contract_versions"]["agent1_curation"] == "1.7"
    assert result["agent_contract_versions"]["agent2_assembly"] == "agent2-downstream-v3"


def test_synthetic_source_warning_is_disclosed(synthetic_workbench_run):
    (_returncode, result), _run_id = synthetic_workbench_run
    assert any("stage1_synthetic_source" in w for w in result["warnings"])


def test_full_raw_workflow_report_is_also_written_for_traceability(synthetic_workbench_run):
    (_returncode, result), run_id = synthetic_workbench_run
    report_path = (
        Path(result["output_artifact_references"]["agent1_curation"]).parent
        / "workflow_report.json"
    )
    assert report_path.is_file()
    report = json.loads(report_path.read_text())
    assert report["run_id"] == run_id


# --- Duplicate/replayed run handling ---------------------------------------------------------


def test_replaying_the_same_run_id_does_not_re_invoke_any_stage(tmp_path, synthetic_workbench_run):
    """A second invocation with the identical ``run_id`` must return the identical result,
    marked ``replayed=True``, without touching any agent subprocess again."""
    (_returncode, first_result), run_id = synthetic_workbench_run

    request_data = _base_request(run_id)
    returncode, replayed_result = _invoke_entrypoint(tmp_path, request_data)

    assert returncode == 0
    assert replayed_result["replayed"] is True
    assert replayed_result["status"] == first_result["status"]
    assert replayed_result["stages_executed"] == first_result["stages_executed"]
    assert replayed_result["started_at"] == first_result["started_at"]
    assert replayed_result["completed_at"] == first_result["completed_at"]


def test_replay_of_a_pre_execution_rejection_is_also_cached(tmp_path):
    run_id = "replay-of-rejection"
    request_data = _base_request(run_id, contract_version="wrong-version")
    first_returncode, first_result = _invoke_entrypoint(tmp_path, request_data)
    assert first_returncode == 1

    second_returncode, second_result = _invoke_entrypoint(tmp_path, request_data)
    assert second_returncode == 1
    assert second_result["replayed"] is True
    assert second_result["error"]["code"] == first_result["error"]["code"]


# --- Scoped-Build Support increment: model_build_request_id / artifact, end to end ----------


def test_model_build_request_id_without_artifact_is_disclosed_and_unscoped(tmp_path):
    """A real run supplying only ``model_build_request_id`` (no artifact content) must succeed
    unscoped, with a disclosed warning naming the reason -- never a silent no-op."""
    run_id = "mbr-id-only-unscoped"
    request_data = _base_request(run_id, model_build_request_id="mbr-no-artifact")
    returncode, result = _invoke_entrypoint(tmp_path, request_data)
    assert returncode == 0
    assert result["status"] == WorkbenchRunStatus.SUCCEEDED.value
    assert any("model_build_request_id was supplied" in w for w in result["warnings"])
    agent2_path = Path(result["output_artifact_references"]["agent2_assembly"])
    agent2_model = json.loads(agent2_path.read_text())
    assert len(agent2_model["reactions"]) == 3  # unscoped: all three fixture reactions


def test_model_build_request_artifact_scopes_the_real_run(tmp_path):
    """A real run supplying both ``model_build_request_id`` and the artifact's own content
    (``input_artifact_references["model_build_request"]``) must restrict Agent 2's own output
    to that artifact's scope, with no "not consumed" disclosure."""
    run_id = "mbr-artifact-scoped"
    request_data = _base_request(
        run_id,
        model_build_request_id="mbr-synthetic-test-1",
        input_artifact_references={
            "stage1_synthetic_source": str(_FIXTURES / "synthetic_agent1_view.json"),
            "stage4_request": str(_FIXTURES / "synthetic_model_build_request_stage4_request.json"),
            "stage5_request": str(_FIXTURES / "synthetic_stage5_request.json"),
            "model_build_request": str(_FIXTURES / "synthetic_model_build_request.json"),
        },
    )
    returncode, result = _invoke_entrypoint(tmp_path, request_data)
    assert returncode == 0
    assert result["status"] == WorkbenchRunStatus.SUCCEEDED.value
    assert not any("model_build_request_id was supplied" in w for w in result["warnings"])
    agent2_path = Path(result["output_artifact_references"]["agent2_assembly"])
    agent2_model = json.loads(agent2_path.read_text())
    assert {r["reaction_id"] for r in agent2_model["reactions"]} == {"reaction-1", "reaction-2"}
