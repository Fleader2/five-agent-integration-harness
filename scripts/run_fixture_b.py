#!/usr/bin/env python3
"""Run Fixture B -- the fully synthetic ground-truth five-agent workflow.

Usage: ``.venv/bin/python3 scripts/run_fixture_b.py [--run-id RUN_ID]``

Agent 1 and Agent 2's own runtime are not invoked for this fixture (disclosed, deliberate scope
decision -- see ``docs/01_orchestration_architecture.md``): the synthetic ground-truth model is
supplied directly as a hand-authored ``agent2_model`` artifact, and Agent 3, Agent 4, and Agent
5 are genuinely, live invoked against it.
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

FIXTURES_DIR = _REPO_ROOT / "tests" / "fixtures"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", default=None)
    args = parser.parse_args()

    run_id = args.run_id or f"synthetic-ground-truth-{uuid.uuid4()}"
    stage_directory = _REPO_ROOT / "artifacts" / "runs" / run_id

    with open(FIXTURES_DIR / "synthetic_stage4_request.json") as f:
        stage4_request = json.load(f)
    with open(FIXTURES_DIR / "synthetic_stage5_request.json") as f:
        stage5_request = json.load(f)

    request = WorkflowRunRequest(
        run_id=run_id, fixture_name="synthetic_ground_truth", stage_directory=str(stage_directory)
    )
    report = run_workflow(
        request,
        stage1_organism_id=None,
        stage2_artifact_source=FIXTURES_DIR / "synthetic_agent2_model.json",
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

    with open(FIXTURES_DIR / "synthetic_ground_truth_manifest.json") as f:
        manifest = json.load(f)
    stage4_path = stage_directory / "stage4_output.json"
    if stage4_path.is_file():
        with open(stage4_path) as f:
            stage4 = json.load(f)
        print("\ntrue vs recovered parameters:")
        for estimate in stage4["calibration"]["parameter_estimates"]:
            true_value = manifest["true_parameters"].get(estimate["target_id"])
            print(
                f"  {estimate['target_id']}: true={true_value} "
                f"fitted={estimate['fitted_value']:.6g} original={estimate['original_value']}"
            )
        print(f"  objective_before={stage4['calibration']['objective_before']}")
        print(f"  objective_after={stage4['calibration']['objective_after']}")

    stage5_path = stage_directory / "stage5_output.json"
    if stage5_path.is_file():
        with open(stage5_path) as f:
            stage5 = json.load(f)
        print("\ntop-ranked experiments:")
        for score in sorted(stage5["experiment_scores"], key=lambda s: s["rank"])[:5]:
            print(
                f"  rank={score['rank']} id={score['experiment_id']} "
                f"score={score['information_score']:.6g}"
            )

    print(f"\nreport written to {report_path}")
    return 0 if report.overall_status.value in ("SUCCESS", "SUCCESS_WITH_EXPECTED_DATA_GAPS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
