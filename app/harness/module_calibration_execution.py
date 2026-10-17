"""Module-Level Agent4 Calibration with Immutable Execution-Condition Provenance increment:
route one accepted hierarchy module's own request to calibrate it through Agent 2 (materialize
this module's own standalone executable artifact), Agent 3 (simulate it, the handoff Agent 4
itself needs), then Agent 4 (calibrate it against Workbench-supplied experimental data) -- the
one, explicit routing point for a *Workbench-selected, durable* module, mirroring
``app.harness.module_simulation``'s own identical role for simulation.

**Deliberately a separate module from ``app.harness.module_calibration``.** That module already
routes one Agent2-*candidate* module through Agent 3 then Agent 4 for the recursive hierarchy
search's own scoring purposes, and maps Agent 4's own report down into a compressed
``ModuleCalibrationEvaluation`` dict a scoring heuristic consumes -- deliberately discarding
per-estimate bounds/provenance, residual arrays, and optimizer diagnostics it has no use for.
This module's own consumer (a Workbench end user wanting full calibration provenance for an
*already-durable, already-accepted* module) needs the opposite: the complete, verbatim
``Agent3Report``/``Agent4Report`` dicts, so nothing here is lost before it ever reaches the
Workbench's own immutable execution-snapshot persistence. Reusing ``module_calibration.py``'s
own compressed mapping would silently drop exactly the fields that persistence needs -- so this
module instead reuses ``app.harness.module_simulation.materialize_module_handoff`` (the
Agent 2 stage) and the same ``runners/run_agent3.py``/``runners/run_agent4.py``/
``app.harness.adapters.build_agent4_handoff`` building blocks ``module_calibration.py`` itself
already reuses -- never a new Agent 2/Agent 3/Agent 4 algorithm, and ``module_calibration.py``
itself is untouched (the recursive hierarchy search's own calibration semantics are unchanged).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.harness.adapters import build_agent4_handoff
from app.harness.module_simulation import ModuleSimulationWorkflowError, materialize_module_handoff
from app.harness.repo_paths import AGENT3, AGENT4
from app.harness.subprocess_runner import run_stage_subprocess
from app.harness.version import MODULE_CALIBRATION_EXECUTION_WORKFLOW_POLICY_VERSION

_RUNNERS_DIR = Path(__file__).resolve().parent / "runners"


class ModuleCalibrationExecutionWorkflowError(ValueError):
    """Raised only for a genuine orchestration/infrastructure defect -- a malformed request
    dict, an ineligible target module (no standalone executable artifact), or an Agent 2/Agent
    3/Agent 4 subprocess crash or timeout -- never for a real, disclosed calibration outcome
    (which Agent 4 itself always reports as data, per ``CalibrationStatus``). Never persisted
    as a cached result: a retry after the underlying problem is fixed must be free to actually
    re-run, never replay a stale infrastructure failure."""


def run_module_calibration_execution_workflow(
    request: dict[str, Any],
    calibration_request: dict[str, Any],
    *,
    stage_dir: str | Path,
    timeout_seconds: float = 300.0,
) -> dict[str, Any]:
    """Route ``request`` through Agent 2 (materialize this module's own standalone executable
    artifact) then Agent 3 (simulate it) then Agent 4 (calibrate it against
    ``calibration_request``, Agent 4's own ``CalibrationRequest`` dict shape, built and
    validated entirely by the Workbench), and return the full, verbatim ``agent3_report``/
    ``agent4_report`` dicts alongside the materialized ``module_handoff``.

    ``request`` keys: ``run_id``, ``agent1_view_path``, ``attach_payload`` (the exact
    ``{"modularization_id", "module_ids", "memberships", "module_ports"}`` dict that
    materializes the target module with its resolved boundary treatment already merged in --
    always a Workbench-reported payload, never invented here), ``module_id`` (the target
    module within it), ``correlation_id``, and optionally ``build_request_path``.

    **Persistence/replay**: the result is written to ``<stage_dir>/module_calibration_
    execution_result_<run_id>.json``; a second call with the identical ``run_id`` reads that
    file back verbatim rather than re-invoking any agent -- mirrors ``run_module_simulation
    _workflow``'s own established replay pattern exactly.
    """
    stage_dir = Path(stage_dir)
    stage_dir.mkdir(parents=True, exist_ok=True)
    run_id = request["run_id"]
    result_path = stage_dir / f"module_calibration_execution_result_{run_id}.json"
    if result_path.is_file():
        with open(result_path) as f:
            return json.load(f)

    try:
        module_handoff = materialize_module_handoff(
            request, stage_dir=stage_dir, timeout_seconds=timeout_seconds
        )
    except ModuleSimulationWorkflowError as exc:
        raise ModuleCalibrationExecutionWorkflowError(str(exc)) from exc

    # Defensive, never-fabricating validation: every calibration target/observation must name
    # a parameter/species the materialized module actually has -- a request referencing an
    # unknown id is rejected clearly, never silently sent to Agent 4 (task instructions §3).
    known_parameter_ids = {p["parameter_id"] for p in module_handoff.get("parameters", [])}
    known_species_ids = {s["species_id"] for s in module_handoff.get("species", [])}
    for target in calibration_request.get("targets", []):
        target_kind = target["target_kind"]
        known_ids = known_parameter_ids if target_kind == "PARAMETER" else known_species_ids
        if target["target_id"] not in known_ids:
            raise ModuleCalibrationExecutionWorkflowError(
                f"calibration target {target['target_id']!r} ({target_kind}) is not a member "
                f"of module {request['module_id']!r}'s own materialized artifact"
            )
    for observation in calibration_request.get("observations", {}).get("observations", []):
        if observation["target_species_id"] not in known_species_ids:
            raise ModuleCalibrationExecutionWorkflowError(
                f"observation target species {observation['target_species_id']!r} is not a "
                f"member of module {request['module_id']!r}'s own materialized artifact"
            )

    module_handoff_path = stage_dir / f"module_simulation_handoff_{run_id}.json"
    agent3_output_path = stage_dir / f"module_calibration_execution_agent3_output_{run_id}.json"
    outcome3 = run_stage_subprocess(
        venv_python=AGENT3.venv_python,
        script_path=_RUNNERS_DIR / "run_agent3.py",
        cwd=AGENT3.repo_dir,
        args=["--input", str(module_handoff_path), "--output", str(agent3_output_path)],
        timeout_seconds=timeout_seconds,
    )
    if outcome3.returncode != 0 or not agent3_output_path.is_file():
        raise ModuleCalibrationExecutionWorkflowError(
            f"Agent 3 subprocess failed for run_id={run_id!r} (returncode="
            f"{outcome3.returncode}, timed_out={outcome3.timed_out}): "
            f"{outcome3.stderr[-500:]!r} -- this is an infrastructure/numerical failure, "
            "never genuine evidence about the proposed module"
        )
    with open(agent3_output_path) as f:
        agent3_report = json.load(f)

    agent4_handoff = build_agent4_handoff(module_handoff, agent3_report)
    agent4_handoff_path = stage_dir / f"module_calibration_execution_agent4_handoff_{run_id}.json"
    with open(agent4_handoff_path, "w") as f:
        json.dump(agent4_handoff, f, indent=2)
    agent4_request_path = stage_dir / f"module_calibration_execution_agent4_request_{run_id}.json"
    with open(agent4_request_path, "w") as f:
        json.dump(calibration_request, f, indent=2)
    agent4_output_path = stage_dir / f"module_calibration_execution_agent4_output_{run_id}.json"
    outcome4 = run_stage_subprocess(
        venv_python=AGENT4.venv_python,
        script_path=_RUNNERS_DIR / "run_agent4.py",
        cwd=AGENT4.repo_dir,
        args=[
            "--handoff",
            str(agent4_handoff_path),
            "--request",
            str(agent4_request_path),
            "--output",
            str(agent4_output_path),
        ],
        timeout_seconds=timeout_seconds,
    )
    if outcome4.returncode != 0 or not agent4_output_path.is_file():
        raise ModuleCalibrationExecutionWorkflowError(
            f"Agent 4 subprocess failed for run_id={run_id!r} (returncode="
            f"{outcome4.returncode}, timed_out={outcome4.timed_out}): "
            f"{outcome4.stderr[-500:]!r} -- this is an infrastructure/numerical failure, "
            "never genuine evidence about the proposed module"
        )
    with open(agent4_output_path) as f:
        agent4_report = json.load(f)

    result = {
        "run_id": run_id,
        "module_id": request["module_id"],
        "modularization_id": request["attach_payload"]["modularization_id"],
        "module_handoff": module_handoff,
        "agent3_report": agent3_report,
        "agent4_report": agent4_report,
        "policy_version": MODULE_CALIBRATION_EXECUTION_WORKFLOW_POLICY_VERSION,
    }
    with open(result_path, "w") as f:
        json.dump(result, f, indent=2)
    return result


__all__ = [
    "MODULE_CALIBRATION_EXECUTION_WORKFLOW_POLICY_VERSION",
    "ModuleCalibrationExecutionWorkflowError",
    "run_module_calibration_execution_workflow",
]
