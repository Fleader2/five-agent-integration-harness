#!/usr/bin/env python3
"""Canonical entrypoint for a Workbench-invoked rebuild of one module's own executable content
from an explicit, possibly-edited reaction selection (Module-Set Edited-Module Materialization
increment).

Usage::

    .venv/bin/python3 scripts/run_workbench_module_rematerialization_request.py \\
        --request /path/to/workbench_module_rematerialization_request.json \\
        --output /path/to/workbench_module_rematerialization_result.json

Mirrors ``run_workbench_module_boundary_derivation_request.py``'s own identical structure and
execution semantics (parse request -> idempotent replay by ``run_id`` -> contract-version check
-> dual-input stage-1 resolution -> run the underlying workflow -> reshape into the Workbench's
own contract shape), pointed at ``app.harness.module_rematerialization
.run_module_rematerialization_workflow`` instead of ``run_module_boundary_derivation_workflow``.
Reports the materialized structure always, and an executable module handoff only once resolved
boundary treatments are also supplied -- never a scientific treatment decision made here.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from app.harness import repo_paths  # noqa: E402
from app.harness.module_rematerialization import (  # noqa: E402
    ModuleRematerializationWorkflowError,
    run_module_rematerialization_workflow,
)
from app.harness.subprocess_runner import run_stage_subprocess  # noqa: E402
from app.harness.workbench_contracts import (  # noqa: E402
    WORKBENCH_MODULE_REMATERIALIZATION_CONTRACT_VERSION,
    WorkbenchModuleRematerializationRequest,
    WorkbenchModuleRematerializationResult,
    WorkbenchRunError,
    WorkbenchRunErrorCode,
    WorkbenchRunStatus,
    module_rematerialization_request_from_dict,
    module_rematerialization_result_from_dict,
    module_rematerialization_result_to_dict,
)

_RUNNERS_DIR = _REPO_ROOT / "app" / "harness" / "runners"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _rejection(
    *, run_id: str, code: WorkbenchRunErrorCode, message: str, warnings: tuple[str, ...] = ()
) -> WorkbenchModuleRematerializationResult:
    now = _now_iso()
    return WorkbenchModuleRematerializationResult(
        contract_version=WORKBENCH_MODULE_REMATERIALIZATION_CONTRACT_VERSION,
        run_id=run_id,
        status=WorkbenchRunStatus.FAILED,
        module_id=None,
        module_handoff=None,
        readiness_blocked_reason=None,
        lineage=None,
        unresolved_dependencies=(),
        started_at=now,
        completed_at=now,
        error=WorkbenchRunError(code=code.value, message=message),
        summary=message,
        warnings=warnings,
    )


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)


def _resolve_agent1_view_path(
    request: WorkbenchModuleRematerializationRequest, *, stage_dir: Path
) -> tuple[Path | None, WorkbenchModuleRematerializationResult | None, str | None]:
    """Returns ``(agent1_view_path, rejection_or_None, warning_or_None)`` -- the identical dual-
    input resolution every other contract in this family already uses."""
    organism_id = request.agent1_organism_id
    synthetic_source = request.input_artifact_references.get("stage1_synthetic_source")
    if (organism_id is None) == (synthetic_source is None):
        return (
            None,
            _rejection(
                run_id=request.run_id,
                code=WorkbenchRunErrorCode.INVALID_STAGE1_INPUT,
                message=(
                    "Exactly one of agent1_organism_id or "
                    "input_artifact_references['stage1_synthetic_source'] must be set."
                ),
            ),
            None,
        )

    if synthetic_source is not None:
        if not Path(synthetic_source).is_file():
            return (
                None,
                _rejection(
                    run_id=request.run_id,
                    code=WorkbenchRunErrorCode.MISSING_INPUT_ARTIFACT,
                    message=f"stage1_synthetic_source is not a readable file: {synthetic_source}",
                ),
                None,
            )
        return (
            Path(synthetic_source),
            None,
            "stage1_synthetic_source was used: Agent 1's own runtime was not invoked. This "
            "path is test/dev-only infrastructure, never a production data source.",
        )

    unavailable = repo_paths.check_repo_available(repo_paths.AGENT1)
    if unavailable is not None:
        return (
            None,
            _rejection(
                run_id=request.run_id,
                code=WorkbenchRunErrorCode.WORKFLOW_FAILED,
                message=f"Agent 1 is not available: {unavailable}",
            ),
            None,
        )
    stage1_output = stage_dir / "stage1_output.json"
    outcome = run_stage_subprocess(
        venv_python=repo_paths.AGENT1.venv_python,
        script_path=_RUNNERS_DIR / "run_agent1.py",
        cwd=repo_paths.AGENT1.repo_dir,
        args=["--organism-id", organism_id, "--output", str(stage1_output)],
    )
    if outcome.returncode != 0 or not stage1_output.is_file():
        return (
            None,
            _rejection(
                run_id=request.run_id,
                code=WorkbenchRunErrorCode.WORKFLOW_FAILED,
                message=f"Agent 1 subprocess failed: {outcome.stderr[-500:]!r}",
            ),
            None,
        )
    return stage1_output, None, None


def _execute(
    request: WorkbenchModuleRematerializationRequest, *, stage_dir: Path
) -> WorkbenchModuleRematerializationResult:
    warnings: list[str] = []
    agent1_view_path, rejection, warning = _resolve_agent1_view_path(request, stage_dir=stage_dir)
    if rejection is not None:
        return rejection
    if warning is not None:
        warnings.append(warning)
    assert agent1_view_path is not None

    started_at = _now_iso()
    try:
        result = run_module_rematerialization_workflow(
            {
                "run_id": request.run_id,
                "agent1_view_path": str(agent1_view_path),
                "attach_payload": request.attach_payload,
                "module_id": request.module_id,
                "module_ports": list(request.module_ports),
                "correlation_id": request.correlation_id,
            },
            stage_dir=stage_dir,
        )
    except ModuleRematerializationWorkflowError as exc:
        return _rejection(
            run_id=request.run_id,
            code=WorkbenchRunErrorCode.MODULE_REMATERIALIZATION_FAILED,
            message=str(exc),
            warnings=tuple(warnings),
        )
    completed_at = _now_iso()

    module_handoff = result["module_handoff"]
    summary = (
        f"module {request.module_id!r}: rematerialized, module_handoff present"
        if module_handoff is not None
        else (
            f"module {request.module_id!r}: rematerialized, not yet simulatable "
            f"({result['readiness_blocked_reason']})"
        )
    )

    return WorkbenchModuleRematerializationResult(
        contract_version=WORKBENCH_MODULE_REMATERIALIZATION_CONTRACT_VERSION,
        run_id=request.run_id,
        status=WorkbenchRunStatus.SUCCEEDED,
        module_id=result["module_id"],
        module_handoff=module_handoff,
        readiness_blocked_reason=result["readiness_blocked_reason"],
        lineage=result["lineage"],
        unresolved_dependencies=tuple(result["unresolved_dependencies"]),
        started_at=started_at,
        completed_at=completed_at,
        error=None,
        summary=summary,
        warnings=tuple(warnings),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output_path = Path(args.output)

    request_data: dict = {}
    try:
        with open(args.request) as f:
            request_data = json.load(f)
        request = module_rematerialization_request_from_dict(request_data)
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        result = _rejection(
            run_id=request_data.get("run_id") or "unknown",
            code=WorkbenchRunErrorCode.MALFORMED_REQUEST,
            message=f"Could not parse request: {exc!r}",
        )
        _write(output_path, module_rematerialization_result_to_dict(result))
        print(f"status={result.status.value} error={result.error.code}")
        return 1

    stage_dir = _REPO_ROOT / "artifacts" / "runs" / request.run_id
    cached_result_path = stage_dir / "workbench_module_rematerialization_result.json"

    if cached_result_path.is_file():
        with open(cached_result_path) as f:
            cached = module_rematerialization_result_from_dict(json.load(f))
        replayed_result = dataclasses.replace(cached, replayed=True)
        _write(output_path, module_rematerialization_result_to_dict(replayed_result))
        print(f"status={replayed_result.status.value} (replayed run_id={request.run_id})")
        return 0 if replayed_result.status is WorkbenchRunStatus.SUCCEEDED else 1

    if request.contract_version != WORKBENCH_MODULE_REMATERIALIZATION_CONTRACT_VERSION:
        result = _rejection(
            run_id=request.run_id,
            code=WorkbenchRunErrorCode.CONTRACT_VERSION_MISMATCH,
            message=(
                "Expected contract_version "
                f"{WORKBENCH_MODULE_REMATERIALIZATION_CONTRACT_VERSION!r}, got "
                f"{request.contract_version!r}."
            ),
        )
    else:
        try:
            result = _execute(request, stage_dir=stage_dir)
        except (KeyError, TypeError) as exc:
            result = _rejection(
                run_id=request.run_id,
                code=WorkbenchRunErrorCode.MALFORMED_REQUEST,
                message=f"Malformed field inside the request (missing/wrong-typed key): {exc!r}",
            )

    _write(cached_result_path, module_rematerialization_result_to_dict(result))
    _write(output_path, module_rematerialization_result_to_dict(result))

    print(f"status={result.status.value}")
    if result.error is not None:
        print(f"  error: {result.error.code} - {result.error.message}")
    for warning in result.warnings:
        print(f"  warning: {warning}")
    return 0 if result.status is WorkbenchRunStatus.SUCCEEDED else 1


if __name__ == "__main__":
    raise SystemExit(main())
