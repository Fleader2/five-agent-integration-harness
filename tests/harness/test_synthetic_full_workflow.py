"""The synthetic ground-truth full-workflow test: calibration recovery, held-out validation,
and experimental-design ranking, all against a known ground truth.

The full five-stage run is run **once** per test session (module-scoped fixture); every test
below only asserts against that one shared result.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.harness.pipeline import run_workflow
from app.harness.types import WorkflowRunRequest, WorkflowStatus

_FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


@pytest.fixture(scope="module")
def synthetic_workflow_report(tmp_path_factory):
    with open(_FIXTURES / "synthetic_stage4_request.json") as f:
        stage4_request = json.load(f)
    with open(_FIXTURES / "synthetic_stage5_request.json") as f:
        stage5_request = json.load(f)
    stage_directory = tmp_path_factory.mktemp("synthetic") / "synthetic-test"
    request = WorkflowRunRequest(
        run_id="synthetic-test",
        fixture_name="synthetic_ground_truth",
        stage_directory=str(stage_directory),
    )
    return run_workflow(
        request,
        stage1_organism_id=None,
        stage2_artifact_source=_FIXTURES / "synthetic_agent2_model.json",
        stage4_request=stage4_request,
        stage5_request=stage5_request,
    )


@pytest.fixture(scope="module")
def synthetic_manifest():
    with open(_FIXTURES / "synthetic_ground_truth_manifest.json") as f:
        return json.load(f)


def test_synthetic_workflow_completes_successfully(synthetic_workflow_report):
    assert synthetic_workflow_report.overall_status is WorkflowStatus.SUCCESS
    assert len(synthetic_workflow_report.stages) == 5
    assert all(
        s.status in (WorkflowStatus.SUCCESS, WorkflowStatus.SUCCESS_WITH_EXPECTED_DATA_GAPS)
        for s in synthetic_workflow_report.stages
    )


def test_synthetic_workflow_all_invariants_pass(synthetic_workflow_report):
    assert len(synthetic_workflow_report.invariant_checks) == 6
    assert all(c.passed for c in synthetic_workflow_report.invariant_checks)


def test_synthetic_workflow_recovers_known_parameters(
    synthetic_workflow_report, synthetic_manifest
):
    stage4_path = Path(synthetic_workflow_report.stages[3].output_artifact_path)
    with open(stage4_path) as f:
        stage4 = json.load(f)
    estimates = {
        e["target_id"]: e["fitted_value"] for e in stage4["calibration"]["parameter_estimates"]
    }
    assert estimates["k1"] == pytest.approx(synthetic_manifest["true_parameters"]["k1"], rel=0.05)
    assert estimates["k2"] == pytest.approx(synthetic_manifest["true_parameters"]["k2"], rel=0.05)
    # k3 is intentionally NOT recoverable from this training set (never observes downstream of
    # S2) -- confirmed flagged, never silently reported as a good fit.
    identifiability = stage4["calibration"]["identifiability_findings"]
    assert any(f["finding_id"] == "low-sensitivity:k3" for f in identifiability)


def test_synthetic_workflow_validates_well_for_identified_parameters(synthetic_workflow_report):
    stage5_path = Path(synthetic_workflow_report.stages[4].output_artifact_path)
    with open(stage5_path) as f:
        stage5 = json.load(f)
    rmse = next(
        m["value"]
        for m in stage5["validation"]["metrics"]
        if m["metric_name"] == "RMSE" and m["partition"] == "VALIDATION"
    )
    assert rmse < 0.01


def test_synthetic_workflow_ranks_the_known_informative_experiment_top(synthetic_workflow_report):
    stage5_path = Path(synthetic_workflow_report.stages[4].output_artifact_path)
    with open(stage5_path) as f:
        stage5 = json.load(f)
    scores_by_id = {s["experiment_id"]: s for s in stage5["experiment_scores"]}
    # Measuring S3 or S4 is the only way to inform the poorly-identified k3 -- either should
    # rank at or near the very top, strictly above every passive measurement of the already-
    # well-identified S1/S2.
    top_rank = min(
        scores_by_id["measure-concentration:S3"]["rank"],
        scores_by_id["measure-concentration:S4"]["rank"],
    )
    assert top_rank <= 1
    assert (
        scores_by_id["measure-concentration:S3"]["information_score"]
        > scores_by_id["measure-concentration:S1"]["information_score"]
    )
