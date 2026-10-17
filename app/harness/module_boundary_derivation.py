"""Boundary-Condition Semantics increment: route one accepted hierarchy module's own request
to derive its *candidate* boundary species through Agent 2 -- the one, explicit routing point,
mirroring ``app.harness.module_simulation``'s own identical role for simulation.

Reports structural candidates only (which species cross the module's own boundary, and in
which direction) -- never a scientific treatment decision, never a fabricated value (task
instructions §5). See ``app/harness/runners/run_agent2_derive_boundary_candidates.py``'s own
module docstring for the exact, pure graph algorithm this reuses -- no new Agent 2 code, no
model construction, nothing about hierarchical recursion or module simulation changed.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.harness.repo_paths import AGENT2
from app.harness.subprocess_runner import run_stage_subprocess
from app.harness.version import MODULE_BOUNDARY_DERIVATION_WORKFLOW_POLICY_VERSION

_RUNNERS_DIR = Path(__file__).resolve().parent / "runners"


class ModuleBoundaryDerivationWorkflowError(ValueError):
    """Raised only for a genuine orchestration/infrastructure defect -- a malformed request
    dict or an Agent 2 subprocess crash or timeout -- never persisted as a cached result: a
    retry after the underlying problem is fixed must be free to actually re-run."""


def run_module_boundary_derivation_workflow(
    request: dict[str, Any], *, stage_dir: str | Path, timeout_seconds: float = 300.0
) -> dict[str, Any]:
    """Route ``request`` through Agent 2, and return ``{"module_id", "candidates": [...]}``
    (each candidate: ``{"species_id", "direction"}``, never a treatment decision).

    ``request`` keys: ``run_id``, ``agent1_view_path``, ``attach_payload`` (the exact
    ``{"modularization_id", "module_ids", "memberships"}`` dict naming the target module --
    always a harness-reported ``HierarchyNodeRecord.attach_payload``, never invented here),
    ``module_id`` (the target module within it), and optionally ``build_request_path``.

    **Persistence/replay**: the result is written to ``<stage_dir>/module_boundary_derivation_
    result_<run_id>.json``; a second call with the identical ``run_id`` reads that file back
    verbatim rather than re-invoking Agent 2 -- mirrors ``run_module_simulation_workflow``'s
    own established replay pattern exactly.
    """
    stage_dir = Path(stage_dir)
    stage_dir.mkdir(parents=True, exist_ok=True)
    run_id = request["run_id"]
    result_path = stage_dir / f"module_boundary_derivation_result_{run_id}.json"
    if result_path.is_file():
        with open(result_path) as f:
            return json.load(f)

    attach_path = stage_dir / f"module_boundary_derivation_attach_{run_id}.json"
    with open(attach_path, "w") as f:
        json.dump(request["attach_payload"], f, indent=2)

    output_path = stage_dir / f"module_boundary_derivation_candidates_{run_id}.json"
    args = [
        "--input",
        str(request["agent1_view_path"]),
        "--output",
        str(output_path),
        "--attach-modularization",
        str(attach_path),
        "--target-module-id",
        request["module_id"],
    ]
    if request.get("build_request_path"):
        args += ["--build-request", str(request["build_request_path"])]

    outcome = run_stage_subprocess(
        venv_python=AGENT2.venv_python,
        script_path=_RUNNERS_DIR / "run_agent2_derive_boundary_candidates.py",
        cwd=AGENT2.repo_dir,
        args=args,
        timeout_seconds=timeout_seconds,
    )
    if outcome.returncode != 0 or not output_path.is_file():
        raise ModuleBoundaryDerivationWorkflowError(
            f"Agent 2 boundary-derivation subprocess failed for run_id={run_id!r} "
            f"(returncode={outcome.returncode}, timed_out={outcome.timed_out}): "
            f"{outcome.stderr[-500:]!r}"
        )
    with open(output_path) as f:
        candidates_result = json.load(f)

    result = {
        "run_id": run_id,
        "module_id": candidates_result["module_id"],
        "candidates": candidates_result["candidates"],
        "policy_version": MODULE_BOUNDARY_DERIVATION_WORKFLOW_POLICY_VERSION,
    }
    with open(result_path, "w") as f:
        json.dump(result, f, indent=2)
    return result


__all__ = [
    "ModuleBoundaryDerivationWorkflowError",
    "run_module_boundary_derivation_workflow",
]
