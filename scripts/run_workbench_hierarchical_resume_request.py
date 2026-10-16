#!/usr/bin/env python3
"""Canonical entrypoint for resuming a paused Workbench-invoked hierarchical recursive
modularization search (human-review/resume increment).

Usage::

    .venv/bin/python3 scripts/run_workbench_hierarchical_resume_request.py \\
        --request /path/to/workbench_hierarchical_resume_request.json \\
        --output /path/to/workbench_hierarchical_run_result.json

See ``docs/15_workbench_hierarchical_recursion_contract.md`` for the full contract
documentation. This script adds a request/result contract around the exact, pre-existing
``app.harness.hierarchical_recursion.resume_hierarchical_recursive_modularization`` mechanism
-- nothing about resume semantics itself is duplicated or reimplemented here, mirroring
``run_workbench_hierarchical_request.py``'s own identical relationship to
``run_hierarchical_recursive_modularization``.

**Execution semantics, in order:**

1. Parse ``--request`` as a ``WorkbenchHierarchicalResumeRequest``
   (``app.harness.workbench_contracts``). A malformed request is reported as
   ``MALFORMED_REQUEST``, never an uncaught exception.
2. **Idempotent replay.** If
   ``artifacts/runs/<run_id>/workbench_hierarchical_resume_result.json`` already exists, it is
   read and returned unchanged, with ``replayed=True`` set on the *returned* copy -- the
   underlying harness resume call is never re-run, and the original cached artifact is never
   rewritten. Each resume attempt is expected to carry its own, fresh ``run_id`` (the Workbench
   is responsible for this, exactly as it already is for the initial-invocation contract).
3. ``contract_version`` is checked against ``WORKBENCH_HIERARCHICAL_RESUME_CONTRACT_VERSION`` --
   a mismatch is ``CONTRACT_VERSION_MISMATCH`` and nothing runs.
4. ``request.checkpoint`` (the Workbench's own stored, verbatim-opaque copy of a prior
   ``WorkbenchHierarchicalRunResult.checkpoint``) is deserialized with
   ``app.harness.hierarchical_recursion.deserialize_checkpoint``, and
   ``resume_hierarchical_recursive_modularization`` is called with it plus
   ``request.decisions`` and a calibration dataset provider that always returns ``None`` (the
   identical disclosed scope note as the initial-invocation entrypoint). A
   ``HierarchicalRecursionCheckpointError`` (malformed/version-mismatched/stale/decision-
   incomplete checkpoint) is reported as ``CHECKPOINT_REJECTED``, never an uncaught exception.
5. The full, unabridged ``HierarchicalRecursionResult`` is written to
   ``hierarchical_recursion_resume_result.json`` for full traceability, and reshaped into the
   identical ``WorkbenchHierarchicalRunResult`` shape the initial-invocation entrypoint
   produces (new ``checkpoint`` populated again when the resumed run paused for review a
   second time), written to both the durable, replayable artifact and ``--output``.

No scientific logic lives here: this script never interprets, repairs, or re-derives any node's
own acceptance decision, nor any checkpoint field -- it only reshapes the already-existing
``HierarchicalRecursionResult`` into the Workbench's own contract shape.
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

from app.harness.hierarchical_recursion import (  # noqa: E402
    HierarchicalRecursionCheckpointError,
    deserialize_checkpoint,
    resume_hierarchical_recursive_modularization,
    serialize_checkpoint,
)
from app.harness.workbench_contracts import (  # noqa: E402
    WORKBENCH_HIERARCHICAL_RESUME_CONTRACT_VERSION,
    WorkbenchHierarchicalResumeRequest,
    WorkbenchHierarchicalRunResult,
    WorkbenchHierarchyNodeSummary,
    WorkbenchRunError,
    WorkbenchRunErrorCode,
    WorkbenchRunStatus,
    hierarchical_result_from_dict,
    hierarchical_result_to_dict,
    hierarchical_resume_request_from_dict,
)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _never_provide_dataset(**_kwargs) -> None:
    """Identical disclosed scope note as ``run_workbench_hierarchical_request.py``'s own --
    every ``CALIBRATE`` decision resolves as ``NO_DATASET_AVAILABLE``, never a fabricated
    dataset."""
    return None


def _rejection(
    *, run_id: str, code: WorkbenchRunErrorCode, message: str, warnings: tuple[str, ...] = ()
) -> WorkbenchHierarchicalRunResult:
    now = _now_iso()
    return WorkbenchHierarchicalRunResult(
        contract_version=WORKBENCH_HIERARCHICAL_RESUME_CONTRACT_VERSION,
        run_id=run_id,
        status=WorkbenchRunStatus.FAILED,
        root_model_id=None,
        nodes=(),
        total_nodes_created=0,
        total_functional_evaluations_used=0,
        total_calibration_runs_used=0,
        requires_user_review=False,
        pending_review_modules=(),
        recursion_policy_version="",
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


def _execute(
    request: WorkbenchHierarchicalResumeRequest, *, stage_dir: Path
) -> WorkbenchHierarchicalRunResult:
    try:
        checkpoint = deserialize_checkpoint(request.checkpoint)
    except (KeyError, TypeError, ValueError) as exc:
        return _rejection(
            run_id=request.run_id,
            code=WorkbenchRunErrorCode.CHECKPOINT_REJECTED,
            message=f"Could not deserialize the stored checkpoint: {exc!r}",
        )

    started_at = _now_iso()
    try:
        result = resume_hierarchical_recursive_modularization(
            checkpoint,
            request.decisions,
            calibration_request_provider=_never_provide_dataset,
        )
    except HierarchicalRecursionCheckpointError as exc:
        return _rejection(
            run_id=request.run_id,
            code=WorkbenchRunErrorCode.CHECKPOINT_REJECTED,
            message=str(exc),
        )
    completed_at = _now_iso()

    warnings = [
        "calibration_request_provider always returns no dataset for this entrypoint -- every "
        "CALIBRATE decision resolves as NO_DATASET_AVAILABLE. See the contract's own disclosed "
        "scope note.",
        *result.warnings,
    ]

    _write(stage_dir / "hierarchical_recursion_resume_result.json", dataclasses.asdict(result))

    nodes = tuple(
        WorkbenchHierarchyNodeSummary(
            node_id=n.node_id,
            depth=n.depth,
            parent_modularization_id=n.parent_modularization_id,
            parent_module_id=n.parent_module_id,
            child_submodel_id=n.child_submodel_id,
            child_modularization_id=n.child_modularization_id,
            child_module_ids=n.child_module_ids,
            accepted=n.accepted,
            reason=n.reason,
            baseline_score=n.baseline_score,
            child_score=n.child_score,
            branch_stopping_reason=(
                n.branch_stopping_reason.value if n.branch_stopping_reason is not None else None
            ),
            recursive_search_stopping_reason=n.recursive_search_stopping_reason,
            recursive_search_rounds=n.recursive_search_rounds,
            recursive_search_policy_version=n.recursive_search_policy_version,
        )
        for n in result.nodes
    )
    accepted_root = next((n for n in result.nodes if n.depth == 0 and n.accepted), None)
    summary = (
        f"resumed: {len(nodes)} node(s) total; {sum(1 for n in nodes if n.accepted)} accepted; "
        f"root accepted={accepted_root is not None}; requires_user_review="
        f"{result.requires_user_review}"
    )

    return WorkbenchHierarchicalRunResult(
        contract_version=WORKBENCH_HIERARCHICAL_RESUME_CONTRACT_VERSION,
        run_id=request.run_id,
        status=WorkbenchRunStatus.SUCCEEDED,
        root_model_id=result.root_model_id or None,
        nodes=nodes,
        total_nodes_created=result.total_nodes_created,
        total_functional_evaluations_used=result.total_functional_evaluations_used,
        total_calibration_runs_used=result.total_calibration_runs_used,
        requires_user_review=result.requires_user_review,
        pending_review_modules=result.pending_review_modules,
        recursion_policy_version=result.policy_version,
        started_at=started_at,
        completed_at=completed_at,
        error=None,
        summary=summary,
        warnings=tuple(warnings),
        checkpoint=serialize_checkpoint(result.checkpoint)
        if result.checkpoint is not None
        else None,
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
        request = hierarchical_resume_request_from_dict(request_data)
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        result = _rejection(
            run_id=request_data.get("run_id") or "unknown",
            code=WorkbenchRunErrorCode.MALFORMED_REQUEST,
            message=f"Could not parse request: {exc!r}",
        )
        _write(output_path, hierarchical_result_to_dict(result))
        print(f"status={result.status.value} error={result.error.code}")
        return 1

    stage_dir = _REPO_ROOT / "artifacts" / "runs" / request.run_id
    cached_result_path = stage_dir / "workbench_hierarchical_resume_result.json"

    if cached_result_path.is_file():
        with open(cached_result_path) as f:
            cached = hierarchical_result_from_dict(json.load(f))
        replayed_result = dataclasses.replace(cached, replayed=True)
        _write(output_path, hierarchical_result_to_dict(replayed_result))
        print(f"status={replayed_result.status.value} (replayed run_id={request.run_id})")
        return 0 if replayed_result.status is WorkbenchRunStatus.SUCCEEDED else 1

    if request.contract_version != WORKBENCH_HIERARCHICAL_RESUME_CONTRACT_VERSION:
        result = _rejection(
            run_id=request.run_id,
            code=WorkbenchRunErrorCode.CONTRACT_VERSION_MISMATCH,
            message=(
                f"Expected contract_version {WORKBENCH_HIERARCHICAL_RESUME_CONTRACT_VERSION!r}, "
                f"got {request.contract_version!r}."
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

    _write(cached_result_path, hierarchical_result_to_dict(result))
    _write(output_path, hierarchical_result_to_dict(result))

    print(f"status={result.status.value}")
    if result.error is not None:
        print(f"  error: {result.error.code} - {result.error.message}")
    for warning in result.warnings:
        print(f"  warning: {warning}")
    return 0 if result.status is WorkbenchRunStatus.SUCCEEDED else 1


if __name__ == "__main__":
    raise SystemExit(main())
