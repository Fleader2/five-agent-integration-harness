"""Recursive Module Evaluation Orchestration: routes one Agent 2 candidate module (already
converted into a standalone executable Antimony submodel by Agent 2's own existing
``generate_module_artifacts`` path, packaged as a ``ModuleCalibrationRequest`` dict) through
Agent 3 then Agent 4, and maps the result back into a structured ``ModuleCalibrationEvaluation``
dict for Agent 2's own ``app.agent2.module_calibration``/``module_evaluation
.calibration_adapter`` to parse.

**Agent 2 never calls Agent 4 (or Agent 3) directly** -- this module is the one, explicit
routing point (task instructions §1). It never imports Agent 2's, Agent 3's, or Agent 4's own
Python package (the identical plain-dict decoupling ``app.harness.adapters`` already uses for
the whole-model pipeline) -- only this module's own documented dict shapes are shared, by
convention, exactly like every other cross-repo boundary in this project.

``request["module_handoff"]`` (built Agent2-side by ``app.agent2.pipeline
.build_module_downstream_handoff``) already declares the identical
``AGENT2_DOWNSTREAM_CONTRACT_VERSION`` a whole-model handoff does, and already carries the
module's own filtered ``species``/``reactions``/``kinetic_laws``/``parameters``/
``antimony_symbol_map`` -- not just a bare Antimony string -- so a real calibration target can
actually be resolved against it by both Agent 3 and Agent 4 unchanged, with zero code change to
either agent.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.harness.adapters import build_agent4_handoff
from app.harness.repo_paths import AGENT3, AGENT4
from app.harness.subprocess_runner import run_stage_subprocess
from app.harness.version import MODULE_CALIBRATION_WORKFLOW_POLICY_VERSION

_RUNNERS_DIR = Path(__file__).resolve().parent / "runners"

#: Agent 4's own ``CalibrationStatus`` -> this module's own ``ModuleCalibrationStatus``.
#: ``INVALID_REQUEST`` is deliberately absent -- it signals a malformed *request* (a caller/
#: orchestration defect), never a genuine calibration outcome, and is raised instead of mapped
#: (see ``_STATUS_MAP`` usage in ``map_calibration_result_to_module_evaluation`` below).
_STATUS_MAP: dict[str, str] = {
    "SUCCESS": "CALIBRATION_SUPPORTED",
    "PARTIAL_SUCCESS": "CALIBRATION_SUPPORTED",
    "UNIDENTIFIABLE": "UNIDENTIFIABLE",
    "INSUFFICIENT_DATA": "INSUFFICIENT_DATA",
    "OPTIMIZATION_FAILED": "CALIBRATION_FAILED",
    "SIMULATION_FAILED": "CALIBRATION_FAILED",
}

#: Identifiability-finding categories treated as "sensitivity to boundary/initial conditions"
#: (task instructions §3) -- the closest existing Agent 4 signal; see
#: ``docs/31_recursive_module_evaluation_orchestration.md`` (agent2-antimony-builder) §5.
_BOUNDARY_SENSITIVITY_CATEGORIES = frozenset({"BOUND_HIT", "LOW_SENSITIVITY"})


class ModuleCalibrationWorkflowError(ValueError):
    """Raised only for a genuine orchestration defect (a malformed request dict, an Agent 4
    ``INVALID_REQUEST`` outcome) -- never for a real, disclosed calibration outcome."""


def build_module_agent3_handoff(request: dict[str, Any]) -> dict[str, Any]:
    """One ``ModuleCalibrationRequest`` dict -> the Agent2->Agent3 handoff dict Agent 3
    consumes unchanged. ``request["module_handoff"]`` is already exactly that shape --
    produced Agent2-side by ``app.agent2.pipeline.build_module_downstream_handoff``, the
    identical, already-filtered (species/reactions/kinetic_laws/parameters/symbol-map) dict a
    whole-model handoff has, scoped to this one module -- so this is pure passthrough, never a
    reshape, and never a second, divergent copy of what Agent 2 itself already built."""
    return dict(request["module_handoff"])


def _residual_sums(residuals: list[dict[str, Any]]) -> tuple[float | None, float | None]:
    total = None
    validation = None
    for r in residuals:
        total = (total or 0.0) + r["sum_squared_residual"]
        if r.get("partition") == "VALIDATION":
            validation = (validation or 0.0) + r["sum_squared_residual"]
    return total, validation


def map_calibration_result_to_module_evaluation(
    request: dict[str, Any],
    agent4_report: dict[str, Any],
    agent3_report: dict[str, Any],
    *,
    evaluation_id: str,
) -> dict[str, Any]:
    """Agent 4's own ``Agent4Report`` dict -> one ``ModuleCalibrationEvaluation`` dict.

    Raises ``ModuleCalibrationWorkflowError`` only for Agent 4's own ``INVALID_REQUEST`` status
    (an orchestration-side request defect, never a calibration outcome) -- every other status
    maps to a real, disclosed ``ModuleCalibrationEvaluation``.
    """
    calibration = agent4_report["calibration"]
    agent4_status = calibration["status"]
    if agent4_status == "INVALID_REQUEST":
        raise ModuleCalibrationWorkflowError(
            f"Agent 4 rejected the calibration request as INVALID_REQUEST: "
            f"{calibration.get('optimizer_message')!r} -- this is a request-construction "
            "defect, never a disclosed calibration outcome"
        )
    status = _STATUS_MAP[agent4_status]

    base: dict[str, Any] = {
        "evaluation_id": evaluation_id,
        "request_id": request["request_id"],
        "correlation_id": request["correlation_id"],
        "run_id": request["run_id"],
        "parent_model_id": request["parent_model_id"],
        "modularization_id": request["modularization_id"],
        "module_id": request["module_id"],
        "status": status,
        "policy_version": MODULE_CALIBRATION_WORKFLOW_POLICY_VERSION,
        "warnings": [],
        "provenance_refs": [
            f"agent4-report::{agent4_report['report_id']}",
            f"agent3-report::{agent3_report['report_id']}",
        ],
    }
    if calibration.get("optimizer_message"):
        base["warnings"].append(calibration["optimizer_message"])

    if status in ("INSUFFICIENT_DATA", "BOUNDARY_INADEQUATE"):
        # Unavailable evidence -- every evidence field below must stay empty/null (never a
        # fabricated partial number alongside a disclosed-unavailable status).
        return base

    total_residual, validation_residual = _residual_sums(calibration.get("residuals", []))
    base["fit_quality"] = {
        "objective_before": calibration.get("objective_before"),
        "objective_after": calibration.get("objective_after"),
        "total_sum_squared_residual": total_residual,
        "validation_sum_squared_residual": validation_residual,
    }
    base["identifiability_findings"] = [
        {
            "finding_id": f["finding_id"],
            "category": f["category"],
            "severity": f["severity"],
            "summary": f["summary"],
            "related_target_ids": f.get("related_target_ids", []),
        }
        for f in calibration.get("identifiability_findings", [])
    ]
    base["parameter_uncertainty"] = [
        {
            "target_id": p["target_id"],
            "fitted_value": p["fitted_value"],
            # Agent 4 computes a covariance matrix internally (for its own HIGH_CORRELATION
            # finding threshold check) but does not expose per-parameter standard errors as
            # public data today -- disclosed as unavailable, never fabricated. See
            # docs/31_recursive_module_evaluation_orchestration.md (agent2-antimony-builder) §5.
            "standard_error": None,
        }
        for p in calibration.get("parameter_estimates", [])
    ]
    base["parameter_correlations"] = []
    base["boundary_sensitivity_findings"] = [
        {
            "target_id": (f.get("related_target_ids") or ["unknown"])[0],
            "category": f["category"],
            "summary": f["summary"],
        }
        for f in calibration.get("identifiability_findings", [])
        if f["category"] in _BOUNDARY_SENSITIVITY_CATEGORIES
    ]
    base["parameters_requiring_external_context"] = []
    base["parameter_stability"] = []
    return base


def run_module_calibration_workflow(
    request: dict[str, Any],
    calibration_request: dict[str, Any],
    *,
    stage_dir: str | Path,
    timeout_seconds: float = 300.0,
) -> dict[str, Any]:
    """Route ``request`` (a ``ModuleCalibrationRequest`` dict) through Agent 3 then Agent 4,
    and return one ``ModuleCalibrationEvaluation`` dict.

    **Persistence/replay**: the result is written to ``<stage_dir>/module_calibration_result_
    <run_id>.json``; a second call with the identical ``run_id`` reads that file back verbatim
    rather than re-invoking either agent (mirrors ``scripts/run_workbench_request.py``'s own
    established replay pattern) -- a real round trip never happens twice for the same run.

    Never calls Agent 4 from inside Agent 2's own process -- this function is the one, explicit
    routing point (task instructions §1).
    """
    stage_dir = Path(stage_dir)
    stage_dir.mkdir(parents=True, exist_ok=True)
    run_id = request["run_id"]
    result_path = stage_dir / f"module_calibration_result_{run_id}.json"
    if result_path.is_file():
        with open(result_path) as f:
            return json.load(f)

    agent3_input = build_module_agent3_handoff(request)
    agent3_input_path = stage_dir / f"module_agent3_input_{run_id}.json"
    with open(agent3_input_path, "w") as f:
        json.dump(agent3_input, f, indent=2)
    agent3_output_path = stage_dir / f"module_agent3_output_{run_id}.json"
    outcome3 = run_stage_subprocess(
        venv_python=AGENT3.venv_python,
        script_path=_RUNNERS_DIR / "run_agent3.py",
        cwd=AGENT3.repo_dir,
        args=["--input", str(agent3_input_path), "--output", str(agent3_output_path)],
        timeout_seconds=timeout_seconds,
    )
    if outcome3.returncode != 0 or not agent3_output_path.is_file():
        result = {
            **{
                k: request[k]
                for k in (
                    "parent_model_id",
                    "modularization_id",
                    "module_id",
                    "request_id",
                    "correlation_id",
                    "run_id",
                )
            },
            "evaluation_id": f"module-calibration::{run_id}::agent3-failed",
            "status": "CALIBRATION_FAILED",
            "policy_version": MODULE_CALIBRATION_WORKFLOW_POLICY_VERSION,
            "warnings": [f"Agent 3 subprocess failed: {outcome3.stderr[-500:]}"],
            "provenance_refs": [],
        }
        with open(result_path, "w") as f:
            json.dump(result, f, indent=2)
        return result
    with open(agent3_output_path) as f:
        agent3_report = json.load(f)

    agent4_handoff = build_agent4_handoff(agent3_input, agent3_report)
    agent4_handoff_path = stage_dir / f"module_agent4_handoff_{run_id}.json"
    with open(agent4_handoff_path, "w") as f:
        json.dump(agent4_handoff, f, indent=2)
    agent4_request_path = stage_dir / f"module_agent4_request_{run_id}.json"
    with open(agent4_request_path, "w") as f:
        json.dump(calibration_request, f, indent=2)
    agent4_output_path = stage_dir / f"module_agent4_output_{run_id}.json"
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
        result = {
            "parent_model_id": request["parent_model_id"],
            "modularization_id": request["modularization_id"],
            "module_id": request["module_id"],
            "request_id": request["request_id"],
            "correlation_id": request["correlation_id"],
            "run_id": run_id,
            "evaluation_id": f"module-calibration::{run_id}::agent4-failed",
            "status": "CALIBRATION_FAILED",
            "policy_version": MODULE_CALIBRATION_WORKFLOW_POLICY_VERSION,
            "warnings": [f"Agent 4 subprocess failed: {outcome4.stderr[-500:]}"],
            "provenance_refs": [],
        }
        with open(result_path, "w") as f:
            json.dump(result, f, indent=2)
        return result
    with open(agent4_output_path) as f:
        agent4_report = json.load(f)

    result = map_calibration_result_to_module_evaluation(
        request,
        agent4_report,
        agent3_report,
        evaluation_id=f"module-calibration::{run_id}",
    )
    with open(result_path, "w") as f:
        json.dump(result, f, indent=2)
    return result


__all__ = [
    "ModuleCalibrationWorkflowError",
    "build_module_agent3_handoff",
    "map_calibration_result_to_module_evaluation",
    "run_module_calibration_workflow",
]
