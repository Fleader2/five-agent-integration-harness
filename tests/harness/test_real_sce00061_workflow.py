"""The real sce00061 (yeast fatty-acid-biosynthesis) full-workflow test.

Requires the live Agent 1 Postgres database (the same one every real fixture in this project's
history has used) to be reachable -- skipped, never failed, if it is not.

The full five-stage run is genuinely expensive (a live database query plus four real agent
subprocess invocations) -- run **once** per test session via a module-scoped fixture, and every
test below only asserts against that one shared result, rather than each re-running the whole
workflow independently.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.harness import repo_paths
from app.harness.pipeline import run_workflow
from app.harness.types import WorkflowRunRequest, WorkflowStatus

_FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
_REAL_ORGANISM_ID = "fc66ef94-9fc1-4a8c-969c-d129c839cb26"


def _db_reachable() -> bool:
    """A pure-stdlib TCP reachability check -- never imports ``psycopg`` directly, since the
    harness's own venv deliberately has zero runtime dependencies (see ``app.harness
    .subprocess_runner``'s own docstring) and does not install Agent 1's database driver."""
    import socket

    try:
        with socket.create_connection(("localhost", 5432), timeout=2):
            return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(
    repo_paths.check_repo_available(repo_paths.AGENT1) is not None or not _db_reachable(),
    reason="Agent 1's live database is not reachable in this environment.",
)


@pytest.fixture(scope="module")
def real_workflow_report(tmp_path_factory):
    with open(_FIXTURES / "sce00061_calibration_request.json") as f:
        stage4_request = json.load(f)
    with open(_FIXTURES / "sce00061_validation_request.json") as f:
        stage5_request = json.load(f)
    stage_directory = tmp_path_factory.mktemp("real-sce00061") / "real-sce00061-test"
    request = WorkflowRunRequest(
        run_id="real-sce00061-test",
        fixture_name="sce00061_real",
        stage_directory=str(stage_directory),
    )
    return run_workflow(
        request,
        stage1_organism_id=_REAL_ORGANISM_ID,
        stage2_artifact_source=_FIXTURES / "sce00061_agent2_model.json",
        stage4_request=stage4_request,
        stage5_request=stage5_request,
    )


def test_real_workflow_completes_with_expected_data_gaps(real_workflow_report):
    assert real_workflow_report.overall_status is WorkflowStatus.SUCCESS_WITH_EXPECTED_DATA_GAPS
    assert len(real_workflow_report.stages) == 5


def test_real_workflow_agent1_curates_real_data(real_workflow_report):
    agent1_stage = real_workflow_report.stages[0]
    assert agent1_stage.status is WorkflowStatus.SUCCESS
    findings = dict(f.split("=") for f in agent1_stage.findings_summary)
    assert int(findings["reactions"]) == 38
    assert int(findings["kinetic_measurements"]) == 216


def test_real_workflow_agent2_reports_executable(real_workflow_report):
    agent2_stage = real_workflow_report.stages[1]
    findings = dict(f.split("=") for f in agent2_stage.findings_summary)
    assert findings["readiness"] == "EXECUTABLE"


def test_real_workflow_agent1_to_agent2_translate_check_passes(real_workflow_report):
    """Beyond the static contract-version comparison, a genuine live check: Agent 2's own real
    ``translate_agent1_view_to_agent2`` entrypoint actually accepts the freshly-curated Agent 1
    view this exact run produced."""
    agent2_stage = real_workflow_report.stages[1]
    findings = dict(f.split("=") for f in agent2_stage.findings_summary)
    assert findings["agent1_to_agent2_translate_ok"] == "True"


def test_real_workflow_agent3_diagnoses_real_model(real_workflow_report):
    agent3_stage = real_workflow_report.stages[2]
    assert any("overall_status=" in f for f in agent3_stage.findings_summary)


def test_real_workflow_agent4_honestly_reports_insufficient_data(real_workflow_report):
    agent4_stage = real_workflow_report.stages[3]
    assert agent4_stage.status is WorkflowStatus.SUCCESS_WITH_EXPECTED_DATA_GAPS
    assert "calibration_status=INSUFFICIENT_DATA" in agent4_stage.findings_summary


def test_real_workflow_agent5_honestly_reports_insufficient_validation_data(real_workflow_report):
    agent5_stage = real_workflow_report.stages[4]
    assert agent5_stage.status is WorkflowStatus.SUCCESS_WITH_EXPECTED_DATA_GAPS
    assert "overall_status=INSUFFICIENT_VALIDATION_DATA" in agent5_stage.findings_summary


def test_real_workflow_all_invariants_pass(real_workflow_report):
    assert all(c.passed for c in real_workflow_report.invariant_checks)


def test_real_workflow_never_fabricates_success(real_workflow_report):
    """The central assertion this fixture exists to make: an honest data gap is never silently
    converted into an unqualified SUCCESS."""
    assert real_workflow_report.overall_status is not WorkflowStatus.SUCCESS
    assert real_workflow_report.overall_status is WorkflowStatus.SUCCESS_WITH_EXPECTED_DATA_GAPS
