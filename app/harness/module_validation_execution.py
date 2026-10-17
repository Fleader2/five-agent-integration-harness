"""Module-Level Agent5 Validation and Experimental Design increment: route one accepted
hierarchy module's own already-calibrated state through Agent 2 (re-materialize this module's
own standalone executable artifact) then Agent 5 (validate the already-fitted, frozen
calibrated parameters against independent held-out observations and recommend informative
follow-up experiments) -- the one, explicit routing point, mirroring
``app.harness.module_calibration_execution``'s own identical role for calibration.

**Deliberately never re-runs Agent 3 or Agent 4.** Agent 5 validates an already-completed
calibration's own frozen parameter estimates -- it is handed the *existing* ``agent4_report``
a prior, already-succeeded module-calibration execution produced (the Workbench's own
responsibility to look up and pass in here, never recomputed), re-materializes only a fresh
Agent 2 model artifact (deterministic given the same ``attach_payload``, so this is never a
second, divergent copy of what calibration itself used), and builds the identical two-key
``Agent5Handoff`` the whole-model ``FULL_PIPELINE``'s own stage4->stage5 transition already
uses (``app.harness.adapters.build_agent5_handoff``, unchanged, reused verbatim) -- no new
Agent 2/4/5 algorithm, and neither ``module_calibration_execution.py`` nor
``module_calibration.py`` is touched.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.harness.adapters import build_agent5_handoff
from app.harness.module_simulation import ModuleSimulationWorkflowError, materialize_module_handoff
from app.harness.repo_paths import AGENT5
from app.harness.subprocess_runner import run_stage_subprocess
from app.harness.version import MODULE_VALIDATION_EXECUTION_WORKFLOW_POLICY_VERSION

_RUNNERS_DIR = Path(__file__).resolve().parent / "runners"


class ModuleValidationExecutionWorkflowError(ValueError):
    """Raised only for a genuine orchestration/infrastructure defect -- a malformed request
    dict, an ineligible target module (no standalone executable artifact), or an Agent 2/Agent
    5 subprocess crash or timeout -- never for a real, disclosed validation outcome (which
    Agent 5 itself always reports as data, per ``ValidationStatus``). Never persisted as a
    cached result: a retry after the underlying problem is fixed must be free to actually
    re-run, never replay a stale infrastructure failure."""


def run_module_validation_execution_workflow(
    request: dict[str, Any],
    agent4_report: dict[str, Any],
    validation_request: dict[str, Any],
    *,
    stage_dir: str | Path,
    timeout_seconds: float = 300.0,
) -> dict[str, Any]:
    """Route ``request`` through Agent 2 (materialize this module's own standalone executable
    artifact) then Agent 5 (validate ``agent4_report``'s own already-fitted parameters against
    ``validation_request``'s own independent observations), and return the full, verbatim
    ``agent5_report`` dict alongside the materialized ``module_handoff``.

    ``request`` keys: ``run_id``, ``agent1_view_path``, ``attach_payload`` (the exact
    ``{"modularization_id", "module_ids", "memberships", "module_ports"}`` dict that
    materializes the target module with its resolved boundary treatment already merged in --
    always a Workbench-reported payload, never invented here), ``module_id`` (the target
    module within it), ``correlation_id``, and optionally ``build_request_path``.

    ``agent4_report`` is the full, verbatim report dict a *prior, already-succeeded*
    module-calibration execution produced -- passed straight through to Agent 5 via
    ``build_agent5_handoff``, never recomputed or re-derived here (Agent 3/Agent 4 are never
    invoked by this workflow).

    ``validation_request`` is a plain dict matching Agent 5's own ``ValidationRequest`` shape
    (``request_id``/``validation_observations``/``candidate_experiments``/...), built and
    validated entirely by the Workbench.

    **Persistence/replay**: the result is written to ``<stage_dir>/module_validation_
    execution_result_<run_id>.json``; a second call with the identical ``run_id`` reads that
    file back verbatim rather than re-invoking any agent -- mirrors ``run_module_calibration
    _execution_workflow``'s own established replay pattern exactly.
    """
    stage_dir = Path(stage_dir)
    stage_dir.mkdir(parents=True, exist_ok=True)
    run_id = request["run_id"]
    result_path = stage_dir / f"module_validation_execution_result_{run_id}.json"
    if result_path.is_file():
        with open(result_path) as f:
            return json.load(f)

    try:
        module_handoff = materialize_module_handoff(
            request, stage_dir=stage_dir, timeout_seconds=timeout_seconds
        )
    except ModuleSimulationWorkflowError as exc:
        raise ModuleValidationExecutionWorkflowError(str(exc)) from exc

    # Defensive, never-fabricating validation: every validation observation must name a
    # species the materialized module actually has -- a request referencing an unknown
    # species is rejected clearly, never silently sent to Agent 5 (task instructions §2).
    known_species_ids = {s["species_id"] for s in module_handoff.get("species", [])}
    for observation in validation_request.get("validation_observations", {}).get(
        "observations", []
    ):
        if observation["target_species_id"] not in known_species_ids:
            raise ModuleValidationExecutionWorkflowError(
                f"validation observation target species {observation['target_species_id']!r} "
                f"is not a member of module {request['module_id']!r}'s own materialized "
                "artifact"
            )

    agent5_handoff = build_agent5_handoff(module_handoff, agent4_report)
    agent5_handoff_path = stage_dir / f"module_validation_execution_agent5_handoff_{run_id}.json"
    with open(agent5_handoff_path, "w") as f:
        json.dump(agent5_handoff, f, indent=2)
    agent5_request_path = stage_dir / f"module_validation_execution_agent5_request_{run_id}.json"
    with open(agent5_request_path, "w") as f:
        json.dump(validation_request, f, indent=2)
    agent5_output_path = stage_dir / f"module_validation_execution_agent5_output_{run_id}.json"
    outcome5 = run_stage_subprocess(
        venv_python=AGENT5.venv_python,
        script_path=_RUNNERS_DIR / "run_agent5.py",
        cwd=AGENT5.repo_dir,
        args=[
            "--handoff",
            str(agent5_handoff_path),
            "--request",
            str(agent5_request_path),
            "--output",
            str(agent5_output_path),
        ],
        timeout_seconds=timeout_seconds,
    )
    if outcome5.returncode != 0 or not agent5_output_path.is_file():
        raise ModuleValidationExecutionWorkflowError(
            f"Agent 5 subprocess failed for run_id={run_id!r} (returncode="
            f"{outcome5.returncode}, timed_out={outcome5.timed_out}): "
            f"{outcome5.stderr[-500:]!r} -- this is an infrastructure/numerical failure, "
            "never genuine evidence about the proposed module"
        )
    with open(agent5_output_path) as f:
        agent5_report = json.load(f)

    result = {
        "run_id": run_id,
        "module_id": request["module_id"],
        "modularization_id": request["attach_payload"]["modularization_id"],
        "module_handoff": module_handoff,
        "agent5_report": agent5_report,
        "policy_version": MODULE_VALIDATION_EXECUTION_WORKFLOW_POLICY_VERSION,
    }
    with open(result_path, "w") as f:
        json.dump(result, f, indent=2)
    return result


__all__ = [
    "MODULE_VALIDATION_EXECUTION_WORKFLOW_POLICY_VERSION",
    "ModuleValidationExecutionWorkflowError",
    "run_module_validation_execution_workflow",
]
