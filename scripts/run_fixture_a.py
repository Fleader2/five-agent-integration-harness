#!/usr/bin/env python3
"""Run Fixture A -- the real sce00061 (yeast fatty-acid-biosynthesis) five-agent workflow.

Usage: ``.venv/bin/python3 scripts/run_fixture_a.py [--run-id RUN_ID]``

See ``docs/05_running_the_fixtures.md`` for what this fixture proves and does not prove.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import uuid
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from app.harness.pipeline import run_workflow  # noqa: E402
from app.harness.types import WorkflowRunRequest  # noqa: E402

REAL_ORGANISM_ID = "fc66ef94-9fc1-4a8c-969c-d129c839cb26"
FIXTURES_DIR = _REPO_ROOT / "tests" / "fixtures"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", default=None)
    args = parser.parse_args()

    run_id = args.run_id or f"sce00061-real-{uuid.uuid4()}"
    stage_directory = _REPO_ROOT / "artifacts" / "runs" / run_id

    with open(FIXTURES_DIR / "sce00061_calibration_request.json") as f:
        stage4_request = json.load(f)
    with open(FIXTURES_DIR / "sce00061_validation_request.json") as f:
        stage5_request = json.load(f)

    request = WorkflowRunRequest(
        run_id=run_id, fixture_name="sce00061_real", stage_directory=str(stage_directory)
    )
    report = run_workflow(
        request,
        stage1_organism_id=REAL_ORGANISM_ID,
        stage4_request=stage4_request,
        stage5_request=stage5_request,
    )

    report_path = stage_directory / "workflow_report.json"
    with open(report_path, "w") as f:
        json.dump(dataclasses.asdict(report), f, indent=2, default=str)

    print(f"overall_status={report.overall_status.value}")
    for stage in report.stages:
        print(f"  [{stage.status.value:32s}] {stage.stage_name:20s} {stage.findings_summary}")
    for check in report.invariant_checks:
        print(f"  [{'PASS' if check.passed else 'FAIL'}] {check.check_id}")
    print(f"report written to {report_path}")
    return 0 if report.overall_status.value in ("SUCCESS", "SUCCESS_WITH_EXPECTED_DATA_GAPS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
