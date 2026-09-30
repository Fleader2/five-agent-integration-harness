"""Version-mismatch tests: confirm the harness stops BEFORE invoking a downstream stage whose
own contract it does not match -- never proceeding against an unexpected shape."""

from __future__ import annotations

import json
from pathlib import Path

from app.harness.pipeline import run_workflow
from app.harness.types import WorkflowRunRequest, WorkflowStatus

_FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def test_corrupted_agent2_contract_version_stops_before_agent3(tmp_path):
    with open(_FIXTURES / "synthetic_agent2_model.json") as f:
        model = json.load(f)
    model["contract_version"] = "not-a-real-contract-version"
    corrupted_path = tmp_path / "corrupted_agent2_model.json"
    with open(corrupted_path, "w") as f:
        json.dump(model, f)

    request = WorkflowRunRequest(
        run_id="version-mismatch-test",
        fixture_name="corrupted",
        stage_directory=str(tmp_path / "stages"),
    )
    report = run_workflow(
        request,
        stage1_organism_id=None,
        stage2_artifact_source=corrupted_path,
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
    assert agent2_stage.expected_contract_version == "agent2-to-agent3-v1"
