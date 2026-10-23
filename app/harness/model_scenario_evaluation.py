"""Whole-Model Experimental-Scenario Evaluation increment: evaluate one experimental scenario
(explicit candidate parameter values, explicit initial-condition/step-intervention overrides,
explicit requested output times) against one whole model's own already-generated Antimony
text -- the one, explicit routing point into Agent 3's own ``app.agent3.scenario_evaluation``,
mirroring ``app.harness.model_antimony_verification``'s identical structure and role.

Deliberately minimal and deliberately **not** calibration: every identifier/value this module's
own request carries must already be a real, resolved value -- which parameter gets which
candidate value, which species/parameter an intervention targets, which rows a dataset's own
times came from -- is the Workbench's own responsibility to have already decided (by validating
against its own authoritative catalogs and dataset rows) before this request is ever built.
This module (and Agent 3 underneath it) only answers "given this exact, already-resolved
scenario, what does the model predict" -- never anything about where the scenario came from, and
never anything about fitting one.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.harness.repo_paths import AGENT3
from app.harness.subprocess_runner import run_stage_subprocess
from app.harness.version import MODEL_SCENARIO_EVALUATION_WORKFLOW_POLICY_VERSION

_RUNNERS_DIR = Path(__file__).resolve().parent / "runners"


class ModelScenarioEvaluationWorkflowError(ValueError):
    """Raised only for a genuine orchestration/infrastructure defect -- an Agent 3 subprocess
    crash, timeout, or malformed output -- never for a disclosed scientific/request-validation
    outcome (``evaluation_status`` carries those). Never persisted as a cached result: a retry
    after the underlying problem is fixed must be free to actually re-run.
    """


def run_model_scenario_evaluation_workflow(
    request: dict[str, Any], *, stage_dir: str | Path, timeout_seconds: float = 300.0
) -> dict[str, Any]:
    """Route ``request`` through Agent 3's own ``evaluate_scenario`` and return
    ``{"evaluation_status", "predictions", "validation_errors", "solver_message",
    "antimony_version", "roadrunner_version"}``.

    ``request`` keys: ``run_id``, ``antimony_text``, ``requested_times``,
    ``requested_output_ids``, ``parameter_overrides``, ``initial_value_overrides``,
    ``interventions`` (a list of ``{"target_kind", "target_id", "time", "value"}`` dicts),
    ``integrator``, ``absolute_tolerance``, ``relative_tolerance``.

    **Persistence/replay**: the result is written to ``<stage_dir>/model_scenario_evaluation_
    result_<run_id>.json``; a second call with the identical ``run_id`` reads that file back
    verbatim rather than re-invoking Agent 3 -- mirrors every other workflow's own established
    replay pattern exactly.
    """
    stage_dir = Path(stage_dir)
    stage_dir.mkdir(parents=True, exist_ok=True)
    run_id = request["run_id"]
    result_path = stage_dir / f"model_scenario_evaluation_result_{run_id}.json"
    if result_path.is_file():
        with open(result_path) as f:
            return json.load(f)

    input_path = stage_dir / f"model_scenario_evaluation_input_{run_id}.json"
    input_path.write_text(json.dumps(request))

    output_path = stage_dir / f"model_scenario_evaluation_output_{run_id}.json"
    outcome = run_stage_subprocess(
        venv_python=AGENT3.venv_python,
        script_path=_RUNNERS_DIR / "run_agent3_evaluate_whole_model_scenario.py",
        cwd=AGENT3.repo_dir,
        args=["--input", str(input_path), "--output", str(output_path)],
        timeout_seconds=timeout_seconds,
    )
    if outcome.returncode != 0 or not output_path.is_file():
        raise ModelScenarioEvaluationWorkflowError(
            f"Agent 3 scenario-evaluation subprocess failed for run_id={run_id!r} (returncode="
            f"{outcome.returncode}, timed_out={outcome.timed_out}): {outcome.stderr[-500:]!r} "
            "-- this is an infrastructure failure, never evidence about the scenario itself"
        )
    with open(output_path) as f:
        evaluation = json.load(f)

    result = {
        "run_id": run_id,
        "evaluation_status": evaluation["evaluation_status"],
        "predictions": evaluation.get("predictions"),
        "validation_errors": evaluation.get("validation_errors", []),
        "solver_message": evaluation.get("solver_message"),
        "antimony_version": evaluation.get("antimony_version"),
        "roadrunner_version": evaluation.get("roadrunner_version"),
        "policy_version": MODEL_SCENARIO_EVALUATION_WORKFLOW_POLICY_VERSION,
    }
    with open(result_path, "w") as f:
        json.dump(result, f, indent=2)
    return result


__all__ = [
    "MODEL_SCENARIO_EVALUATION_WORKFLOW_POLICY_VERSION",
    "ModelScenarioEvaluationWorkflowError",
    "run_model_scenario_evaluation_workflow",
]
