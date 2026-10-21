"""Module-Set Edited-Module Materialization increment: route one Workbench-supplied, explicit
reaction selection through Agent 2 to correctly rebuild that module's own executable content --
the one, explicit routing point, mirroring ``app.harness.module_boundary_derivation``'s/
``app.harness.module_simulation``'s own identical role for their own increments.

Produces the materialized structure (retained species/reactions/parameters/lineage) always, and
an executable module handoff only once the caller also supplies resolved boundary treatments
(``module_ports``) -- a genuine "materialized, not yet simulatable" outcome is never an error.
See ``app/harness/runners/run_agent2_rematerialize_module.py``'s own module docstring for why
this needs one new step (``materialize_submodel``) beyond what the two existing, unmodified
``run_agent2_*.py`` runners already do -- no new Agent 2 code, no duplicated closure logic.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.harness.repo_paths import AGENT2
from app.harness.subprocess_runner import run_stage_subprocess
from app.harness.version import MODULE_REMATERIALIZATION_WORKFLOW_POLICY_VERSION

_RUNNERS_DIR = Path(__file__).resolve().parent / "runners"


class ModuleRematerializationWorkflowError(ValueError):
    """Raised only for a genuine orchestration/infrastructure defect -- a malformed request
    dict or an Agent 2 subprocess crash, timeout, or scientific rejection (an unknown reaction
    id, a selection with zero reactions) -- never persisted as a cached result: a retry after
    the underlying problem is fixed must be free to actually re-run."""


def run_module_rematerialization_workflow(
    request: dict[str, Any], *, stage_dir: str | Path, timeout_seconds: float = 300.0
) -> dict[str, Any]:
    """Route ``request`` through Agent 2, and return ``{"module_id", "module_handoff",
    "readiness_blocked_reason", "lineage", "unresolved_dependencies"}`` (see
    ``run_agent2_rematerialize_module.py``'s own docstring for the exact shape of each).

    ``request`` keys: ``run_id``, ``agent1_view_path``, ``attach_payload`` (the exact
    ``{"modularization_id", "module_ids", "memberships"}`` dict naming the Workbench's own
    edited, REACTION-only selection for the target module -- never species/parameters/etc.,
    which this workflow's own Agent 2 call derives correctly), ``module_id`` (the target module
    within it), optionally ``module_ports`` (the scientist's own resolved boundary treatments
    for this exact selection, as ``[{"port_id", "module_id", "species_id", "direction",
    "externally_controlled", "initial_value", "unit"}, ...]``), and optionally
    ``build_request_path``.

    **Persistence/replay**: the result is written to ``<stage_dir>/module_rematerialization_
    result_<run_id>.json``; a second call with the identical ``run_id`` reads that file back
    verbatim rather than re-invoking Agent 2 -- mirrors ``run_module_boundary_derivation
    _workflow``'s own established replay pattern exactly.
    """
    stage_dir = Path(stage_dir)
    stage_dir.mkdir(parents=True, exist_ok=True)
    run_id = request["run_id"]
    result_path = stage_dir / f"module_rematerialization_result_{run_id}.json"
    if result_path.is_file():
        with open(result_path) as f:
            return json.load(f)

    attach_path = stage_dir / f"module_rematerialization_attach_{run_id}.json"
    with open(attach_path, "w") as f:
        json.dump(request["attach_payload"], f, indent=2)

    output_path = stage_dir / f"module_rematerialization_output_{run_id}.json"
    args = [
        "--input",
        str(request["agent1_view_path"]),
        "--output",
        str(output_path),
        "--attach-modularization",
        str(attach_path),
        "--target-module-id",
        request["module_id"],
        "--correlation-id",
        request.get("correlation_id") or run_id,
        "--run-id",
        run_id,
    ]
    module_ports = request.get("module_ports")
    if module_ports:
        ports_path = stage_dir / f"module_rematerialization_ports_{run_id}.json"
        with open(ports_path, "w") as f:
            json.dump(module_ports, f, indent=2)
        args += ["--module-ports", str(ports_path)]
    if request.get("build_request_path"):
        args += ["--build-request", str(request["build_request_path"])]

    outcome = run_stage_subprocess(
        venv_python=AGENT2.venv_python,
        script_path=_RUNNERS_DIR / "run_agent2_rematerialize_module.py",
        cwd=AGENT2.repo_dir,
        args=args,
        timeout_seconds=timeout_seconds,
    )
    if outcome.returncode != 0 or not output_path.is_file():
        raise ModuleRematerializationWorkflowError(
            f"Agent 2 rematerialization subprocess failed for run_id={run_id!r} "
            f"(returncode={outcome.returncode}, timed_out={outcome.timed_out}): "
            f"{outcome.stderr[-500:]!r}"
        )
    with open(output_path) as f:
        rematerialization_result = json.load(f)

    result = {
        "run_id": run_id,
        "module_id": rematerialization_result["module_id"],
        "module_handoff": rematerialization_result["module_handoff"],
        "readiness_blocked_reason": rematerialization_result["readiness_blocked_reason"],
        "lineage": rematerialization_result["lineage"],
        "unresolved_dependencies": rematerialization_result["unresolved_dependencies"],
        "policy_version": MODULE_REMATERIALIZATION_WORKFLOW_POLICY_VERSION,
    }
    with open(result_path, "w") as f:
        json.dump(result, f, indent=2)
    return result


__all__ = [
    "ModuleRematerializationWorkflowError",
    "run_module_rematerialization_workflow",
]
