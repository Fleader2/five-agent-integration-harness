#!/usr/bin/env python3
"""Canonical entrypoint for a Workbench-invoked verification of one whole model's own
already-generated Antimony text (Model-Species Catalog Prerequisite increment).

Usage::

    .venv/bin/python3 scripts/run_workbench_model_antimony_verification_request.py \\
        --request /path/to/workbench_model_antimony_verification_request.json \\
        --output /path/to/workbench_model_antimony_verification_result.json

Mirrors every other ``run_workbench_*_request.py`` entrypoint's own identical structure and
execution semantics, pointed at ``app.harness.model_antimony_verification
.run_model_antimony_verification_workflow`` instead -- the one, deliberate difference being
that this contract needs no Agent 1/2 input resolution at all: the Workbench already has the
Antimony text in hand from its own prior full-model build, and sends it directly.
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

from app.harness.model_antimony_verification import (  # noqa: E402
    ModelAntimonyVerificationWorkflowError,
    run_model_antimony_verification_workflow,
)
from app.harness.workbench_contracts import (  # noqa: E402
    WORKBENCH_MODEL_ANTIMONY_VERIFICATION_CONTRACT_VERSION,
    WorkbenchModelAntimonyVerificationRequest,
    WorkbenchModelAntimonyVerificationResult,
    WorkbenchRunError,
    WorkbenchRunErrorCode,
    WorkbenchRunStatus,
    model_antimony_verification_request_from_dict,
    model_antimony_verification_result_from_dict,
    model_antimony_verification_result_to_dict,
)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _rejection(
    *, run_id: str, code: WorkbenchRunErrorCode, message: str
) -> WorkbenchModelAntimonyVerificationResult:
    now = _now_iso()
    return WorkbenchModelAntimonyVerificationResult(
        contract_version=WORKBENCH_MODEL_ANTIMONY_VERIFICATION_CONTRACT_VERSION,
        run_id=run_id,
        status=WorkbenchRunStatus.FAILED,
        load_succeeded=False,
        load_message=None,
        floating_species_ids=(),
        boundary_species_ids=(),
        compartment_ids=(),
        antimony_version=None,
        roadrunner_version=None,
        started_at=now,
        completed_at=now,
        error=WorkbenchRunError(code=code.value, message=message),
        summary=message,
    )


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)


def _execute(
    request: WorkbenchModelAntimonyVerificationRequest, *, stage_dir: Path
) -> WorkbenchModelAntimonyVerificationResult:
    started_at = _now_iso()
    try:
        result = run_model_antimony_verification_workflow(
            {"run_id": request.run_id, "antimony_text": request.antimony_text},
            stage_dir=stage_dir,
        )
    except ModelAntimonyVerificationWorkflowError as exc:
        return _rejection(
            run_id=request.run_id,
            code=WorkbenchRunErrorCode.WORKFLOW_FAILED,
            message=str(exc),
        )
    completed_at = _now_iso()

    summary = f"model antimony text verified: load_succeeded={result['load_succeeded']!r}"
    return WorkbenchModelAntimonyVerificationResult(
        contract_version=WORKBENCH_MODEL_ANTIMONY_VERIFICATION_CONTRACT_VERSION,
        run_id=request.run_id,
        status=WorkbenchRunStatus.SUCCEEDED,
        load_succeeded=result["load_succeeded"],
        load_message=result["load_message"],
        floating_species_ids=tuple(result["floating_species_ids"]),
        boundary_species_ids=tuple(result["boundary_species_ids"]),
        compartment_ids=tuple(result["compartment_ids"]),
        antimony_version=result["antimony_version"],
        roadrunner_version=result["roadrunner_version"],
        started_at=started_at,
        completed_at=completed_at,
        error=None,
        summary=summary,
        global_parameter_ids=tuple(result.get("global_parameter_ids", ())),
        assignment_rule_derived_parameter_ids=tuple(
            result.get("assignment_rule_derived_parameter_ids", ())
        ),
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
        request = model_antimony_verification_request_from_dict(request_data)
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        result = _rejection(
            run_id=request_data.get("run_id") or "unknown",
            code=WorkbenchRunErrorCode.MALFORMED_REQUEST,
            message=f"Could not parse request: {exc!r}",
        )
        _write(output_path, model_antimony_verification_result_to_dict(result))
        print(f"status={result.status.value} error={result.error.code}")
        return 1

    stage_dir = _REPO_ROOT / "artifacts" / "runs" / request.run_id
    cached_result_path = stage_dir / "workbench_model_antimony_verification_result.json"

    if cached_result_path.is_file():
        with open(cached_result_path) as f:
            cached = model_antimony_verification_result_from_dict(json.load(f))
        replayed_result = dataclasses.replace(cached, replayed=True)
        _write(output_path, model_antimony_verification_result_to_dict(replayed_result))
        print(f"status={replayed_result.status.value} (replayed run_id={request.run_id})")
        return 0 if replayed_result.status is WorkbenchRunStatus.SUCCEEDED else 1

    if request.contract_version != WORKBENCH_MODEL_ANTIMONY_VERIFICATION_CONTRACT_VERSION:
        result = _rejection(
            run_id=request.run_id,
            code=WorkbenchRunErrorCode.CONTRACT_VERSION_MISMATCH,
            message=(
                "Expected contract_version "
                f"{WORKBENCH_MODEL_ANTIMONY_VERIFICATION_CONTRACT_VERSION!r}, got "
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

    _write(cached_result_path, model_antimony_verification_result_to_dict(result))
    _write(output_path, model_antimony_verification_result_to_dict(result))

    print(f"status={result.status.value}")
    if result.error is not None:
        print(f"  error: {result.error.code} - {result.error.message}")
    return 0 if result.status is WorkbenchRunStatus.SUCCEEDED else 1


if __name__ == "__main__":
    raise SystemExit(main())
