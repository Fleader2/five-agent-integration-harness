"""Module-Set Edited-Module Materialization increment, Phase B: route a Workbench module-set
member's own explicit reaction selection and scientist-resolved boundary treatments through
Agent 2 (correct rebuild via ``app.harness.module_rematerialization``) then Agent 3 (simulate
the rebuilt artifact) -- the one, explicit routing point, mirroring
``app.harness.module_simulation``'s own identical role for an unedited module.

Reuses Agent 3's own, already-existing, unchanged ``run_agent3.py`` runner (the identical one
every other module-scoped simulation/calibration/validation workflow already invokes) -- no new
Agent 3 algorithm. Reuses ``run_module_rematerialization_workflow`` as a library call for its
own materialization step, rather than duplicating that logic -- the one difference from
``app.harness.module_simulation.run_module_simulation_workflow`` is which materialization
function supplies the handoff (this one correctly recomputes the closure for an edited
selection; that one trusts an already-complete, previously-decided ``attach_payload``
verbatim).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.harness.module_rematerialization import (
    ModuleRematerializationWorkflowError,
    run_module_rematerialization_workflow,
)
from app.harness.repo_paths import AGENT3
from app.harness.subprocess_runner import run_stage_subprocess
from app.harness.version import MODULE_SET_SIMULATION_WORKFLOW_POLICY_VERSION

_RUNNERS_DIR = Path(__file__).resolve().parent / "runners"


class ModuleSetSimulationWorkflowError(ValueError):
    """Raised only for a genuine orchestration/infrastructure defect -- a malformed request, an
    unknown reaction id, a rebuilt module with no eligible standalone executable artifact (no
    resolved boundary treatments, or an insufficient one), or an Agent 2/Agent 3 subprocess
    crash or timeout -- never for a real, disclosed simulation outcome (Agent 3 itself always
    reports that as data). Never persisted as a cached result: a retry after the underlying
    problem is fixed must be free to actually re-run.
    """


def run_module_set_simulation_workflow(
    request: dict[str, Any], *, stage_dir: str | Path, timeout_seconds: float = 300.0
) -> dict[str, Any]:
    """Route ``request`` through Agent 2 (correctly rebuild the module from its own explicit
    reaction selection and resolved boundary treatments) then Agent 3 (simulate it), and return
    Agent 3's own ``Agent3Report`` dict alongside the rebuild's own lineage.

    ``request`` keys: ``run_id``, ``agent1_view_path``, ``attach_payload`` (REACTION-only
    memberships for the target module's own current, possibly-edited selection), ``module_id``,
    ``module_ports`` (the scientist's own resolved boundary treatments for this exact
    selection -- required for this workflow to produce anything simulatable; an empty/missing
    value is reported as a failure here, not silently materialized-only, since this workflow's
    entire purpose is simulation), ``correlation_id``, and optionally ``build_request_path``.

    **Persistence/replay**: the result is written to ``<stage_dir>/module_set_simulation_
    result_<run_id>.json``; a second call with the identical ``run_id`` reads that file back
    verbatim rather than re-invoking either agent -- mirrors ``run_module_simulation_workflow``'s
    own established replay pattern exactly.
    """
    stage_dir = Path(stage_dir)
    stage_dir.mkdir(parents=True, exist_ok=True)
    run_id = request["run_id"]
    result_path = stage_dir / f"module_set_simulation_result_{run_id}.json"
    if result_path.is_file():
        with open(result_path) as f:
            return json.load(f)

    if not request.get("module_ports"):
        raise ModuleSetSimulationWorkflowError(
            f"run_id={run_id!r}: no resolved boundary treatments (module_ports) were supplied "
            "-- this workflow only ever simulates, never materializes-only; use "
            "run_module_rematerialization_workflow directly for a structure-only rebuild."
        )

    try:
        rematerialization_result = run_module_rematerialization_workflow(
            {
                "run_id": run_id,
                "agent1_view_path": request["agent1_view_path"],
                "attach_payload": request["attach_payload"],
                "module_id": request["module_id"],
                "module_ports": request["module_ports"],
                "correlation_id": request.get("correlation_id"),
            },
            stage_dir=stage_dir,
            timeout_seconds=timeout_seconds,
        )
    except ModuleRematerializationWorkflowError as exc:
        raise ModuleSetSimulationWorkflowError(
            f"Agent 2 rematerialization failed for run_id={run_id!r}: {exc}"
        ) from exc

    module_handoff = rematerialization_result["module_handoff"]
    if module_handoff is None:
        raise ModuleSetSimulationWorkflowError(
            f"run_id={run_id!r}: rebuilt module has no eligible standalone executable artifact "
            f"({rematerialization_result['readiness_blocked_reason']})"
        )

    module_handoff_path = stage_dir / f"module_set_simulation_handoff_{run_id}.json"
    with open(module_handoff_path, "w") as f:
        json.dump(module_handoff, f, indent=2)

    agent3_output_path = stage_dir / f"module_set_simulation_agent3_output_{run_id}.json"
    outcome3 = run_stage_subprocess(
        venv_python=AGENT3.venv_python,
        script_path=_RUNNERS_DIR / "run_agent3.py",
        cwd=AGENT3.repo_dir,
        args=["--input", str(module_handoff_path), "--output", str(agent3_output_path)],
        timeout_seconds=timeout_seconds,
    )
    if outcome3.returncode != 0 or not agent3_output_path.is_file():
        raise ModuleSetSimulationWorkflowError(
            f"Agent 3 subprocess failed for run_id={run_id!r} (returncode="
            f"{outcome3.returncode}, timed_out={outcome3.timed_out}): "
            f"{outcome3.stderr[-500:]!r} -- this is an infrastructure/numerical failure, "
            "never genuine evidence about the rebuilt module"
        )
    with open(agent3_output_path) as f:
        agent3_report = json.load(f)

    result = {
        "run_id": run_id,
        "module_id": request["module_id"],
        "module_handoff_summary": {
            "model_id": module_handoff.get("model_id"),
            "species_count": len(module_handoff.get("species", [])),
            "reaction_count": len(module_handoff.get("reactions", [])),
            "parameter_count": len(module_handoff.get("parameters", [])),
        },
        "lineage": rematerialization_result["lineage"],
        "agent3_report": agent3_report,
        "policy_version": MODULE_SET_SIMULATION_WORKFLOW_POLICY_VERSION,
    }
    with open(result_path, "w") as f:
        json.dump(result, f, indent=2)
    return result


__all__ = [
    "MODULE_SET_SIMULATION_WORKFLOW_POLICY_VERSION",
    "ModuleSetSimulationWorkflowError",
    "run_module_set_simulation_workflow",
]
