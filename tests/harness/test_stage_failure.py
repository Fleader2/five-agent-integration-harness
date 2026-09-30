"""Stage-failure tests: confirm a genuine agent-side crash is reported as
``WorkflowStatus.AGENT_STAGE_FAILED`` (never raised, never silently treated as success)."""

from __future__ import annotations

import json
from pathlib import Path

from app.harness.pipeline import run_workflow
from app.harness.types import WorkflowRunRequest, WorkflowStatus

_FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def test_missing_required_field_fails_agent3_stage_cleanly(tmp_path):
    with open(_FIXTURES / "synthetic_agent2_model.json") as f:
        model = json.load(f)
    del model["antimony_text"]  # Agent 3's own parser requires this field.
    broken_path = tmp_path / "broken_agent2_model.json"
    with open(broken_path, "w") as f:
        json.dump(model, f)

    request = WorkflowRunRequest(
        run_id="stage-failure-test", fixture_name="broken", stage_directory=str(tmp_path / "stages")
    )
    report = run_workflow(
        request,
        stage1_organism_id=None,
        stage2_artifact_source=broken_path,
        stage4_request={
            "request_id": "unused",
            "targets": [],
            "observations": {"observation_set_id": "x", "observations": []},
        },
        stage5_request={
            "request_id": "unused",
            "validation_observations": {"observation_set_id": "x", "observations": []},
        },
    )
    assert report.overall_status is WorkflowStatus.AGENT_STAGE_FAILED
    agent3_stage = next(s for s in report.stages if s.stage_name == "agent3_simulation")
    assert agent3_stage.status is WorkflowStatus.AGENT_STAGE_FAILED
    assert agent3_stage.message is not None
    assert "HandoffContractError" in agent3_stage.message or "antimony_text" in agent3_stage.message


def test_invalid_json_output_reported_as_invalid_artifact(tmp_path, monkeypatch):
    """A stage whose own output file is not valid JSON is reported as ``INVALID_ARTIFACT``,
    never crashing the harness itself."""
    from app.harness import pipeline as pipeline_module
    from app.harness.subprocess_runner import SubprocessStageOutcome

    def _fake_run_stage_subprocess(*, venv_python, script_path, cwd, args, timeout_seconds=300.0):
        # Simulate a stage whose script "succeeds" (exit 0) but writes garbage.
        output_arg_index = args.index("--output") + 1
        Path(args[output_arg_index]).write_text("{ this is not valid json")
        return SubprocessStageOutcome(
            returncode=0, stdout="", stderr="", elapsed_seconds=0.01, timed_out=False
        )

    monkeypatch.setattr(pipeline_module, "run_stage_subprocess", _fake_run_stage_subprocess)

    request = WorkflowRunRequest(
        run_id="invalid-artifact-test",
        fixture_name="synthetic_ground_truth",
        stage_directory=str(tmp_path / "stages"),
    )
    report = run_workflow(
        request,
        stage1_organism_id=None,
        stage2_artifact_source=_FIXTURES / "synthetic_agent2_model.json",
        stage4_request={
            "request_id": "unused",
            "targets": [],
            "observations": {"observation_set_id": "x", "observations": []},
        },
        stage5_request={
            "request_id": "unused",
            "validation_observations": {"observation_set_id": "x", "observations": []},
        },
    )
    assert report.overall_status is WorkflowStatus.INVALID_ARTIFACT
