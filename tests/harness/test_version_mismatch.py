"""Version-mismatch tests: confirm the harness stops BEFORE invoking a downstream stage whose
own contract it does not match -- never proceeding against an unexpected shape."""

from __future__ import annotations

import json
from pathlib import Path

from app.harness.pipeline import run_workflow
from app.harness.subprocess_runner import SubprocessStageOutcome
from app.harness.subprocess_runner import run_stage_subprocess as _real_run_stage_subprocess
from app.harness.types import WorkflowRunRequest, WorkflowStatus

_FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def test_corrupted_agent2_contract_version_stops_before_agent3(tmp_path, monkeypatch):
    """**Five-Agent Workflow V1 Hardening increment:** Stage 2 is now always a live subprocess
    invocation, never a copy of a static artifact -- so a corrupted Agent 2 output is simulated
    by intercepting that one subprocess call, rather than by pointing at a pre-corrupted file."""
    from app.harness import pipeline as pipeline_module

    with open(_FIXTURES / "sample_agent2_downstream_model.json") as f:
        corrupted_model = json.load(f)
    corrupted_model["contract_version"] = "not-a-real-contract-version"

    def _fake_run_stage_subprocess(*, venv_python, script_path, cwd, args, timeout_seconds=300.0):
        if Path(script_path).name == "run_agent2.py":
            output_arg_index = args.index("--output") + 1
            Path(args[output_arg_index]).write_text(json.dumps(corrupted_model))
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
        run_id="version-mismatch-test",
        fixture_name="corrupted",
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
    assert report.overall_status is WorkflowStatus.CONTRACT_MISMATCH
    stage_names = [s.stage_name for s in report.stages]
    assert "agent3_simulation" not in stage_names
    agent2_stage = next(s for s in report.stages if s.stage_name == "agent2_assembly")
    assert agent2_stage.status is WorkflowStatus.CONTRACT_MISMATCH
    assert agent2_stage.declared_contract_version == "not-a-real-contract-version"
    assert agent2_stage.expected_contract_version == "agent2-downstream-v1"
