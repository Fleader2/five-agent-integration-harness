"""Deterministic-rerun comparison: the same fixture run twice must produce identical stage
statuses, identical calibration results, and identical experiment rankings.

Exactly two full five-stage runs are performed for this whole module (module-scoped fixture,
shared across every test below) -- the point of this test file is comparing those same two
runs from several angles, not re-running the workflow once per assertion.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.harness.pipeline import run_workflow
from app.harness.synthetic_fixture import patch_synthetic_ground_truth_initial_conditions
from app.harness.types import WorkflowRunRequest

_FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def _run(stage_directory, run_id):
    with open(_FIXTURES / "synthetic_stage4_request.json") as f:
        stage4_request = json.load(f)
    with open(_FIXTURES / "synthetic_stage5_request.json") as f:
        stage5_request = json.load(f)
    request = WorkflowRunRequest(
        run_id=run_id, fixture_name="synthetic_ground_truth", stage_directory=str(stage_directory)
    )
    return run_workflow(
        request,
        stage1_organism_id=None,
        stage1_synthetic_source=_FIXTURES / "synthetic_agent1_view.json",
        stage2_postprocess=patch_synthetic_ground_truth_initial_conditions,
        stage4_request=stage4_request,
        stage5_request=stage5_request,
    )


@pytest.fixture(scope="module")
def two_runs(tmp_path_factory):
    base = tmp_path_factory.mktemp("rerun")
    report1 = _run(base / "rerun-1", "rerun-1")
    report2 = _run(base / "rerun-2", "rerun-2")
    return report1, report2


def test_two_runs_produce_identical_stage_statuses(two_runs):
    report1, report2 = two_runs
    assert report1.overall_status == report2.overall_status
    assert [s.status for s in report1.stages] == [s.status for s in report2.stages]


def test_two_runs_produce_identical_calibration_results(two_runs):
    report1, report2 = two_runs
    with open(report1.stages[3].output_artifact_path) as f:
        stage4_a = json.load(f)
    with open(report2.stages[3].output_artifact_path) as f:
        stage4_b = json.load(f)
    estimates_a = {
        e["target_id"]: e["fitted_value"] for e in stage4_a["calibration"]["parameter_estimates"]
    }
    estimates_b = {
        e["target_id"]: e["fitted_value"] for e in stage4_b["calibration"]["parameter_estimates"]
    }
    assert estimates_a == estimates_b
    assert stage4_a["calibration"]["objective_after"] == stage4_b["calibration"]["objective_after"]


def test_two_runs_produce_identical_experiment_rankings(two_runs):
    report1, report2 = two_runs
    with open(report1.stages[4].output_artifact_path) as f:
        stage5_a = json.load(f)
    with open(report2.stages[4].output_artifact_path) as f:
        stage5_b = json.load(f)
    ranks_a = {s["experiment_id"]: s["rank"] for s in stage5_a["experiment_scores"]}
    ranks_b = {s["experiment_id"]: s["rank"] for s in stage5_b["experiment_scores"]}
    assert ranks_a == ranks_b


def test_two_runs_produce_byte_identical_stage2_artifact(two_runs):
    """**Five-Agent Workflow V1 Hardening increment:** Stage 2 is now a live, genuine invocation
    of Agent 2's own canonical orchestration entrypoint (plus the one deterministic,
    id-keyed-not-uuid-keyed harness-side initial-condition patch for this synthetic fixture) --
    never a straight copy of a static fixture file. Agent 2's own pipeline embeds no fresh
    ``uuid.uuid4()``-based id anywhere in its output (confirmed by
    ``agent2-antimony-builder``'s own ``test_is_deterministic``), unlike every downstream
    stage's own report (each of which embeds at least one fresh run-scoped id, by design, per
    Agents 3-5's own contracts -- including inside ``provenance_refs`` values, not only
    top-level id fields, which makes a generic "strip every id field and compare the rest" check
    for those reports more fragile than it is worth -- never a determinism defect). Stage 2's
    own output therefore still genuinely must be byte-identical (and therefore
    checksum-identical) across reruns. The substantive content checks above (statuses, fitted
    parameter values, objective, rankings) are what actually establish "the science is
    reproducible" for the stages that carry fresh ids; this check adds the one stage where
    byte-identity itself is the correct, meaningful bar.
    """
    report1, report2 = two_runs
    stage2_checksum_1 = report1.stages[1].output_checksum
    stage2_checksum_2 = report2.stages[1].output_checksum
    assert stage2_checksum_1 is not None
    assert stage2_checksum_1 == stage2_checksum_2
