"""Scoped-Build Support increment: a real, live, subprocess-level Workbench -> Harness ->
Agent 2 scoped-build run, using the synthetic ground-truth fixture
(``tests/fixtures/synthetic_model_build_request.json``, requiring only ``reaction-1``/
``reaction-2`` of the fixture's three-reaction chain).

This is the increment's own "real cross-repo integration" requirement: a genuine
``run_workflow`` call, with a real ``--build-request`` artifact forwarded all the way to a real
Agent 2 subprocess invocation in Agent 2's own venv -- never mocked.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.harness.pipeline import run_workflow
from app.harness.synthetic_fixture import patch_synthetic_ground_truth_initial_conditions
from app.harness.types import WorkflowRunRequest, WorkflowStatus

_FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


@pytest.fixture(scope="module")
def scoped_workflow_report(tmp_path_factory):
    with open(_FIXTURES / "synthetic_model_build_request_stage4_request.json") as f:
        stage4_request = json.load(f)
    with open(_FIXTURES / "synthetic_stage5_request.json") as f:
        stage5_request = json.load(f)
    stage_directory = tmp_path_factory.mktemp("scoped") / "scoped-build-test"
    request = WorkflowRunRequest(
        run_id="scoped-build-test",
        fixture_name="synthetic_ground_truth_scoped",
        stage_directory=str(stage_directory),
    )
    return run_workflow(
        request,
        stage1_organism_id=None,
        stage1_synthetic_source=_FIXTURES / "synthetic_agent1_view.json",
        stage2_postprocess=patch_synthetic_ground_truth_initial_conditions,
        stage2_build_request_path=_FIXTURES / "synthetic_model_build_request.json",
        stage4_request=stage4_request,
        stage5_request=stage5_request,
    )


def test_scoped_workflow_completes(scoped_workflow_report):
    assert scoped_workflow_report.overall_status in (
        WorkflowStatus.SUCCESS,
        WorkflowStatus.SUCCESS_WITH_EXPECTED_DATA_GAPS,
    )
    assert len(scoped_workflow_report.stages) == 5


def test_scoped_agent2_output_is_restricted_to_the_required_reactions(scoped_workflow_report):
    agent2_stage = next(
        s for s in scoped_workflow_report.stages if s.stage_name == "agent2_assembly"
    )
    assert agent2_stage.status is WorkflowStatus.SUCCESS
    with open(agent2_stage.output_artifact_path) as f:
        agent2_model = json.load(f)
    assert {r["reaction_id"] for r in agent2_model["reactions"]} == {"reaction-1", "reaction-2"}


def test_scoped_agent2_stage_carries_no_scoping_warning_for_a_fully_resolved_request(
    scoped_workflow_report,
):
    agent2_stage = next(
        s for s in scoped_workflow_report.stages if s.stage_name == "agent2_assembly"
    )
    assert not any("UNRESOLVED" in w for w in agent2_stage.warnings)


def test_unscoped_and_scoped_runs_against_the_identical_fixture_differ(scoped_workflow_report):
    """Sanity check that scoping is actually doing something, not a no-op: the unscoped
    synthetic fixture (``tests/harness/test_synthetic_full_workflow.py``) assembles all three
    reactions; this scoped run assembles only two."""
    agent2_stage = next(
        s for s in scoped_workflow_report.stages if s.stage_name == "agent2_assembly"
    )
    with open(agent2_stage.output_artifact_path) as f:
        agent2_model = json.load(f)
    assert len(agent2_model["reactions"]) == 2
