"""Executable-Module Materialization increment: route one accepted hierarchy module's own
request to simulate it through Agent 2 (materialize this module's own standalone executable
artifact) then Agent 3 (simulate it) -- the one, explicit routing point, mirroring
``app.harness.module_calibration``'s own identical role for calibration.

**Agent 2 never calls Agent 3 directly** -- this module is that one routing point. It never
imports Agent 2's or Agent 3's own Python package -- only the documented plain-dict shapes are
shared, the identical cross-repo-subprocess-only discipline every other module in this harness
already follows.

Reuses Agent 3's own, already-existing, unchanged ``run_agent3.py`` runner (the identical one
Stage 3 of the five-agent ``FULL_PIPELINE`` and ``app.harness.module_calibration`` both already
invoke) -- no new Agent 3 simulation algorithm, and Agent 3 receives exactly the selected
module's own filtered handoff, never the whole root model's.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.harness.repo_paths import AGENT2, AGENT3
from app.harness.subprocess_runner import run_stage_subprocess
from app.harness.version import MODULE_SIMULATION_WORKFLOW_POLICY_VERSION

_RUNNERS_DIR = Path(__file__).resolve().parent / "runners"


class ModuleSimulationWorkflowError(ValueError):
    """Raised only for a genuine orchestration/infrastructure defect -- a malformed request
    dict, an ineligible target module (no standalone executable artifact), or an Agent 2/Agent
    3 subprocess crash or timeout -- never for a real, disclosed simulation outcome (which
    Agent 3 itself always reports as data, per ``SimulationStatus``). Never persisted as a
    cached result: a retry after the underlying problem is fixed must be free to actually
    re-run, never replay a stale infrastructure failure.
    """


def run_module_simulation_workflow(
    request: dict[str, Any], *, stage_dir: str | Path, timeout_seconds: float = 300.0
) -> dict[str, Any]:
    """Route ``request`` through Agent 2 (materialize this module's own standalone executable
    artifact) then Agent 3 (simulate it), and return Agent 3's own ``Agent3Report`` dict.

    ``request`` keys: ``run_id``, ``agent1_view_path``, ``attach_payload`` (the exact
    ``{"modularization_id", "module_ids", "memberships"}`` dict that materializes the target
    module -- always a harness-reported ``HierarchyNodeRecord.attach_payload``, never invented
    here), ``module_id`` (the target module within ``attach_payload``), ``correlation_id``, and
    optionally ``build_request_path``.

    **Persistence/replay**: the result is written to ``<stage_dir>/module_simulation_result_
    <run_id>.json``; a second call with the identical ``run_id`` reads that file back verbatim
    rather than re-invoking either agent -- mirrors ``run_module_calibration_workflow``'s own
    established replay pattern exactly.
    """
    stage_dir = Path(stage_dir)
    stage_dir.mkdir(parents=True, exist_ok=True)
    run_id = request["run_id"]
    result_path = stage_dir / f"module_simulation_result_{run_id}.json"
    if result_path.is_file():
        with open(result_path) as f:
            return json.load(f)

    attach_path = stage_dir / f"module_simulation_attach_{run_id}.json"
    with open(attach_path, "w") as f:
        json.dump(request["attach_payload"], f, indent=2)

    module_handoff_path = stage_dir / f"module_simulation_handoff_{run_id}.json"
    agent2_args = [
        "--input",
        str(request["agent1_view_path"]),
        "--output",
        str(module_handoff_path),
        "--attach-modularization",
        str(attach_path),
        "--target-module-id",
        request["module_id"],
        "--correlation-id",
        request["correlation_id"],
        "--run-id",
        run_id,
    ]
    if request.get("build_request_path"):
        agent2_args += ["--build-request", str(request["build_request_path"])]

    outcome2 = run_stage_subprocess(
        venv_python=AGENT2.venv_python,
        script_path=_RUNNERS_DIR / "run_agent2_materialize_module_handoff.py",
        cwd=AGENT2.repo_dir,
        args=agent2_args,
        timeout_seconds=timeout_seconds,
    )
    if outcome2.returncode != 0 or not module_handoff_path.is_file():
        # Covers both a genuine infrastructure failure and a disclosed-but-fatal
        # ModuleCalibrationReferenceError (the target module has no eligible standalone
        # artifact) -- either way, there is no module_handoff to simulate, so this is raised,
        # never persisted as a cached outcome (task instructions: "invalid/non-executable
        # module rejected clearly").
        raise ModuleSimulationWorkflowError(
            f"Agent 2 module materialization subprocess failed for run_id={run_id!r} "
            f"(returncode={outcome2.returncode}, timed_out={outcome2.timed_out}): "
            f"{outcome2.stderr[-500:]!r}"
        )
    with open(module_handoff_path) as f:
        module_handoff = json.load(f)

    agent3_output_path = stage_dir / f"module_simulation_agent3_output_{run_id}.json"
    outcome3 = run_stage_subprocess(
        venv_python=AGENT3.venv_python,
        script_path=_RUNNERS_DIR / "run_agent3.py",
        cwd=AGENT3.repo_dir,
        args=["--input", str(module_handoff_path), "--output", str(agent3_output_path)],
        timeout_seconds=timeout_seconds,
    )
    if outcome3.returncode != 0 or not agent3_output_path.is_file():
        raise ModuleSimulationWorkflowError(
            f"Agent 3 subprocess failed for run_id={run_id!r} (returncode="
            f"{outcome3.returncode}, timed_out={outcome3.timed_out}): "
            f"{outcome3.stderr[-500:]!r} -- this is an infrastructure/numerical failure, "
            "never genuine evidence about the proposed module"
        )
    with open(agent3_output_path) as f:
        agent3_report = json.load(f)

    result = {
        "run_id": run_id,
        "module_id": request["module_id"],
        "modularization_id": request["attach_payload"]["modularization_id"],
        "module_handoff_summary": {
            "model_id": module_handoff.get("model_id"),
            "species_count": len(module_handoff.get("species", [])),
            "reaction_count": len(module_handoff.get("reactions", [])),
            "parameter_count": len(module_handoff.get("parameters", [])),
        },
        "agent3_report": agent3_report,
        "policy_version": MODULE_SIMULATION_WORKFLOW_POLICY_VERSION,
    }
    with open(result_path, "w") as f:
        json.dump(result, f, indent=2)
    return result


__all__ = [
    "MODULE_SIMULATION_WORKFLOW_POLICY_VERSION",
    "ModuleSimulationWorkflowError",
    "run_module_simulation_workflow",
]
