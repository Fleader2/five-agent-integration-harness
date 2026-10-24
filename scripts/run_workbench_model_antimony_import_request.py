#!/usr/bin/env python3
"""Canonical entrypoint for a Workbench-invoked Antimony-import fidelity audit (Whole-Model
Antimony Import increment).

Usage::

    .venv/bin/python3 scripts/run_workbench_model_antimony_import_request.py \\
        --request /path/to/workbench_model_antimony_import_request.json \\
        --output /path/to/workbench_model_antimony_import_result.json

Mirrors ``scripts/run_workbench_model_antimony_verification_request.py``'s own identical
structure and execution semantics, pointed at ``app.harness.model_antimony_import
.run_model_antimony_import_workflow`` instead -- Agent 2's own import fidelity audit, never a
replacement for that verification contract's own real executability check, which the Workbench
still calls separately, unchanged, against the identical Antimony text.
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

from app.harness.model_antimony_import import (  # noqa: E402
    ModelAntimonyImportWorkflowError,
    run_model_antimony_import_workflow,
)
from app.harness.workbench_contracts import (  # noqa: E402
    WORKBENCH_MODEL_ANTIMONY_IMPORT_CONTRACT_VERSION,
    WorkbenchModelAntimonyImportRequest,
    WorkbenchModelAntimonyImportResult,
    WorkbenchRunError,
    WorkbenchRunErrorCode,
    WorkbenchRunStatus,
    model_antimony_import_request_from_dict,
    model_antimony_import_result_from_dict,
    model_antimony_import_result_to_dict,
)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _rejection(
    *, run_id: str, code: WorkbenchRunErrorCode, message: str
) -> WorkbenchModelAntimonyImportResult:
    now = _now_iso()
    return WorkbenchModelAntimonyImportResult(
        contract_version=WORKBENCH_MODEL_ANTIMONY_IMPORT_CONTRACT_VERSION,
        run_id=run_id,
        status=WorkbenchRunStatus.FAILED,
        import_succeeded=False,
        import_error_kind=None,
        import_message=None,
        compartment_ids=(),
        compartment_names={},
        species_ids=(),
        species_compartment_ids={},
        parameter_ids=(),
        reaction_ids=(),
        assignment_rule_count=0,
        rate_rule_count=0,
        algebraic_rule_count=0,
        event_count=0,
        antimony_import_parser_version=None,
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
    request: WorkbenchModelAntimonyImportRequest, *, stage_dir: Path
) -> WorkbenchModelAntimonyImportResult:
    started_at = _now_iso()
    try:
        result = run_model_antimony_import_workflow(
            {"run_id": request.run_id, "antimony_text": request.antimony_text},
            stage_dir=stage_dir,
        )
    except ModelAntimonyImportWorkflowError as exc:
        return _rejection(
            run_id=request.run_id,
            code=WorkbenchRunErrorCode.MODEL_ANTIMONY_IMPORT_FAILED,
            message=str(exc),
        )
    completed_at = _now_iso()

    summary = f"antimony import audited: import_succeeded={result['import_succeeded']!r}"
    return WorkbenchModelAntimonyImportResult(
        contract_version=WORKBENCH_MODEL_ANTIMONY_IMPORT_CONTRACT_VERSION,
        run_id=request.run_id,
        status=WorkbenchRunStatus.SUCCEEDED,
        import_succeeded=result["import_succeeded"],
        import_error_kind=result.get("import_error_kind"),
        import_message=result.get("import_message"),
        compartment_ids=tuple(result.get("compartment_ids", ())),
        compartment_names=dict(result.get("compartment_names", {})),
        species_ids=tuple(result.get("species_ids", ())),
        species_compartment_ids=dict(result.get("species_compartment_ids", {})),
        parameter_ids=tuple(result.get("parameter_ids", ())),
        reaction_ids=tuple(result.get("reaction_ids", ())),
        assignment_rule_count=result.get("assignment_rule_count", 0),
        rate_rule_count=result.get("rate_rule_count", 0),
        algebraic_rule_count=result.get("algebraic_rule_count", 0),
        event_count=result.get("event_count", 0),
        antimony_import_parser_version=result.get("antimony_import_parser_version"),
        started_at=started_at,
        completed_at=completed_at,
        error=None,
        summary=summary,
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
        request = model_antimony_import_request_from_dict(request_data)
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        result = _rejection(
            run_id=request_data.get("run_id") or "unknown",
            code=WorkbenchRunErrorCode.MALFORMED_REQUEST,
            message=f"Could not parse request: {exc!r}",
        )
        _write(output_path, model_antimony_import_result_to_dict(result))
        print(f"status={result.status.value} error={result.error.code}")
        return 1

    stage_dir = _REPO_ROOT / "artifacts" / "runs" / request.run_id
    cached_result_path = stage_dir / "workbench_model_antimony_import_result.json"

    if cached_result_path.is_file():
        with open(cached_result_path) as f:
            cached = model_antimony_import_result_from_dict(json.load(f))
        replayed_result = dataclasses.replace(cached, replayed=True)
        _write(output_path, model_antimony_import_result_to_dict(replayed_result))
        print(f"status={replayed_result.status.value} (replayed run_id={request.run_id})")
        return 0 if replayed_result.status is WorkbenchRunStatus.SUCCEEDED else 1

    if request.contract_version != WORKBENCH_MODEL_ANTIMONY_IMPORT_CONTRACT_VERSION:
        result = _rejection(
            run_id=request.run_id,
            code=WorkbenchRunErrorCode.CONTRACT_VERSION_MISMATCH,
            message=(
                "Expected contract_version "
                f"{WORKBENCH_MODEL_ANTIMONY_IMPORT_CONTRACT_VERSION!r}, got "
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

    _write(cached_result_path, model_antimony_import_result_to_dict(result))
    _write(output_path, model_antimony_import_result_to_dict(result))

    print(f"status={result.status.value}")
    if result.error is not None:
        print(f"  error: {result.error.code} - {result.error.message}")
    return 0 if result.status is WorkbenchRunStatus.SUCCEEDED else 1


if __name__ == "__main__":
    raise SystemExit(main())
