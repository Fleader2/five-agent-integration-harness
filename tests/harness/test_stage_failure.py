"""Stage-failure tests: confirm a genuine agent-side crash is reported as
``WorkflowStatus.AGENT_STAGE_FAILED`` (never raised, never silently treated as success)."""

from __future__ import annotations

import json
from pathlib import Path

from app.harness.pipeline import run_workflow
from app.harness.subprocess_runner import SubprocessStageOutcome
from app.harness.subprocess_runner import run_stage_subprocess as _real_run_stage_subprocess
from app.harness.types import WorkflowRunRequest, WorkflowStatus

_FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def test_missing_required_field_fails_agent3_stage_cleanly(tmp_path, monkeypatch):
    """**Five-Agent Workflow V1 Hardening increment:** Stage 2 is now always a live subprocess
    invocation, so a malformed Agent 2 output is simulated by intercepting that one subprocess
    call and letting Stage 3's own real subprocess run against it -- never by pointing Stage 2
    at a pre-corrupted static file."""
    from app.harness import pipeline as pipeline_module

    with open(_FIXTURES / "sample_agent2_downstream_model.json") as f:
        model = json.load(f)
    del model["antimony_text"]  # Agent 3's own parser requires this field.

    def _fake_run_stage_subprocess(*, venv_python, script_path, cwd, args, timeout_seconds=300.0):
        if Path(script_path).name == "run_agent2.py":
            output_arg_index = args.index("--output") + 1
            Path(args[output_arg_index]).write_text(json.dumps(model))
            return SubprocessStageOutcome(
                returncode=0, stdout="", stderr="", elapsed_seconds=0.01, timed_out=False
            )
        return _real_run_stage_subprocess(
            venv_python=venv_python,
            script_path=script_path,
            cwd=cwd,
            args=args,
            timeout_seconds=timeout_seconds,
        )

    monkeypatch.setattr(pipeline_module, "run_stage_subprocess", _fake_run_stage_subprocess)

    request = WorkflowRunRequest(
        run_id="stage-failure-test", fixture_name="broken", stage_directory=str(tmp_path / "stages")
    )
    report = run_workflow(
        request,
        stage1_organism_id=None,
        stage1_synthetic_source=_FIXTURES / "synthetic_agent1_view.json",
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
        stage1_synthetic_source=_FIXTURES / "synthetic_agent1_view.json",
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
