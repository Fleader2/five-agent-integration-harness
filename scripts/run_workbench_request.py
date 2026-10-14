#!/usr/bin/env python3
"""Canonical entrypoint for a Workbench-invoked five-agent workflow run.

Usage::

    .venv/bin/python3 scripts/run_workbench_request.py \\
        --request /path/to/workbench_invocation_request.json \\
        --output /path/to/workbench_run_result.json

See ``docs/07_workbench_harness_contract.md`` for the full contract
documentation. In one sentence: this script is the one, documented way the
Workbench (or anything else) asks this harness to run the five-agent
workflow, and it never does anything the harness's own existing
``app.harness.pipeline.run_workflow``/``scripts/run_fixture_{a,b}.py``
scripts did not already do -- it only adds a request/result contract
around that exact, pre-existing mechanism.

**Execution semantics, in order:**

1. Parse ``--request`` as a ``WorkbenchInvocationRequest``
   (``app.harness.workbench_contracts``). A malformed request (missing
   required field, invalid JSON) is reported as ``MALFORMED_REQUEST`` and
   never raises an uncaught exception.
2. **Idempotent replay.** If ``artifacts/runs/<run_id>/workbench_result.json``
   already exists (a prior completed invocation of this exact ``run_id``),
   that cached result is read and returned, with ``replayed=True`` set on
   the *returned* copy -- no agent is re-invoked, and the original cached
   artifact is never rewritten. A ``run_id`` is a caller-chosen idempotency
   key, exactly like every other Workbench natural key in this project's
   family; reusing one is a replay, not a new attempt.
3. ``contract_version`` is checked against
   ``WORKBENCH_HARNESS_CONTRACT_VERSION`` -- a mismatch is
   ``CONTRACT_VERSION_MISMATCH`` and no stage runs.
4. ``requested_entry_stage`` must be ``SUPPORTED_ENTRY_STAGE``
   (``"FULL_PIPELINE"``) -- the only mode ``run_workflow`` actually
   implements. Any other value is ``UNSUPPORTED_ENTRY_STAGE``, a disclosed
   gap, not a silent fallback to the full pipeline.
5. Exactly one of ``agent1_organism_id`` or
   ``input_artifact_references["stage1_synthetic_source"]`` must be set
   (mirroring ``run_workflow``'s own requirement) -- otherwise
   ``INVALID_STAGE1_INPUT``. The synthetic-source path is test/dev-only
   infrastructure, documented as such.
6. ``input_artifact_references["stage4_request"]``/``["stage5_request"]``
   must each name a readable JSON file -- otherwise
   ``MISSING_INPUT_ARTIFACT``. The Workbench never needs to understand
   Agent 4's/Agent 5's own request shape to supply these: it only stores
   and forwards a reference to a file it (or a human) already produced.
7. ``model_build_request_id``, if supplied, is recorded in the result's
   own ``warnings`` -- the disclosed gap: Agent 2 has no mechanism to
   consume a scoped build request yet (see
   ``docs/07_workbench_harness_contract.md``).
8. The real ``run_workflow`` runs, exactly as either existing fixture
   script invokes it. Its own ``FiveAgentWorkflowReport`` is written in
   full to ``workflow_report.json`` (unchanged, for full traceability),
   and mapped onto a ``WorkbenchRunResult`` written to both
   ``artifacts/runs/<run_id>/workbench_result.json`` (the durable,
   replayable artifact) and ``--output`` (this invocation's own copy).

No scientific logic lives here: this script never interprets, repairs, or
re-derives any agent's own output -- it only orchestrates the exact same
subprocess chain the existing fixture scripts already run, and reshapes
the already-existing ``FiveAgentWorkflowReport`` into the Workbench's own
contract shape.
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

from app.harness.pipeline import run_workflow  # noqa: E402
from app.harness.synthetic_fixture import (  # noqa: E402
    patch_synthetic_ground_truth_initial_conditions,
)
from app.harness.types import WorkflowRunRequest, WorkflowStatus  # noqa: E402
from app.harness.workbench_contracts import (  # noqa: E402
    SUPPORTED_ENTRY_STAGE,
    WORKBENCH_HARNESS_CONTRACT_VERSION,
    WorkbenchInvocationRequest,
    WorkbenchRunError,
    WorkbenchRunErrorCode,
    WorkbenchRunResult,
    WorkbenchRunStatus,
    request_from_dict,
    result_from_dict,
    result_to_dict,
)

_SUCCESS_STATUSES = (WorkflowStatus.SUCCESS, WorkflowStatus.SUCCESS_WITH_EXPECTED_DATA_GAPS)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _rejection(
    *, run_id: str, code: WorkbenchRunErrorCode, message: str, warnings: tuple[str, ...] = ()
) -> WorkbenchRunResult:
    """A deterministic, pre-execution rejection -- no stage was ever invoked."""
    now = _now_iso()
    return WorkbenchRunResult(
        contract_version=WORKBENCH_HARNESS_CONTRACT_VERSION,
        run_id=run_id,
        status=WorkbenchRunStatus.FAILED,
        stages_executed=(),
        output_artifact_references={},
        model_artifact_reference=None,
        agent_contract_versions={},
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
    request: WorkbenchInvocationRequest, *, stage_directory: Path, warnings: list[str]
) -> WorkbenchRunResult:
    has_organism = request.agent1_organism_id is not None
    synthetic_source = request.input_artifact_references.get("stage1_synthetic_source")
    has_synthetic = synthetic_source is not None
    if has_organism == has_synthetic:
        return _rejection(
            run_id=request.run_id,
            code=WorkbenchRunErrorCode.INVALID_STAGE1_INPUT,
            message=(
                "Exactly one of agent1_organism_id or "
                "input_artifact_references['stage1_synthetic_source'] must be set."
            ),
        )

    stage4_request_path = request.input_artifact_references.get("stage4_request")
    stage5_request_path = request.input_artifact_references.get("stage5_request")
    missing = [
        name
        for name, value in (
            ("stage4_request", stage4_request_path),
            ("stage5_request", stage5_request_path),
        )
        if value is None or not Path(value).is_file()
    ]
    if missing:
        return _rejection(
            run_id=request.run_id,
            code=WorkbenchRunErrorCode.MISSING_INPUT_ARTIFACT,
            message=f"Missing or unreadable input_artifact_references: {missing}",
        )

    with open(stage4_request_path) as f:
        stage4_request = json.load(f)
    with open(stage5_request_path) as f:
        stage5_request = json.load(f)

    if request.model_build_request_id is not None:
        warnings.append(
            "model_build_request_id was supplied but is not yet consumed: Agent 2 has no "
            "mechanism to accept a scoped build request, so the full curated knowledge view "
            "was used unscoped. See docs/07_workbench_harness_contract.md."
        )

    workflow_request = WorkflowRunRequest(
        run_id=request.run_id,
        fixture_name=f"workbench:{request.project_id}:{request.subproject_id}",
        stage_directory=str(stage_directory),
    )

    started_at = _now_iso()
    if has_synthetic:
        report = run_workflow(
            workflow_request,
            stage1_organism_id=None,
            stage1_synthetic_source=Path(synthetic_source),
            stage2_postprocess=patch_synthetic_ground_truth_initial_conditions,
            stage4_request=stage4_request,
            stage5_request=stage5_request,
        )
        warnings.append(
            "stage1_synthetic_source was used: Agent 1's own runtime was not invoked. This "
            "path is test/dev-only infrastructure, never a production data source."
        )
    else:
        report = run_workflow(
            workflow_request,
            stage1_organism_id=request.agent1_organism_id,
            stage4_request=stage4_request,
            stage5_request=stage5_request,
        )
    completed_at = _now_iso()

    report_path = stage_directory / "workflow_report.json"
    _write(report_path, dataclasses.asdict(report))

    output_artifact_references = {
        s.stage_name: s.output_artifact_path for s in report.stages if s.output_artifact_path
    }
    agent_contract_versions = {s.stage_name: s.declared_contract_version for s in report.stages}
    succeeded = report.overall_status in _SUCCESS_STATUSES

    error = None
    if not succeeded:
        failing_stage = next((s for s in report.stages if s.status == report.overall_status), None)
        error = WorkbenchRunError(
            code=WorkbenchRunErrorCode.WORKFLOW_FAILED.value,
            message=report.sufficiency_note,
            stage_name=failing_stage.stage_name if failing_stage else None,
        )

    return WorkbenchRunResult(
        contract_version=WORKBENCH_HARNESS_CONTRACT_VERSION,
        run_id=request.run_id,
        status=WorkbenchRunStatus.SUCCEEDED if succeeded else WorkbenchRunStatus.FAILED,
        stages_executed=tuple(s.stage_name for s in report.stages),
        output_artifact_references=output_artifact_references,
        model_artifact_reference=output_artifact_references.get("agent2_assembly"),
        agent_contract_versions=agent_contract_versions,
        started_at=started_at,
        completed_at=completed_at,
        error=error,
        summary=report.sufficiency_note,
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
        request = request_from_dict(request_data)
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        result = _rejection(
            run_id=request_data.get("run_id") or "unknown",
            code=WorkbenchRunErrorCode.MALFORMED_REQUEST,
            message=f"Could not parse request: {exc!r}",
        )
        _write(output_path, result_to_dict(result))
        print(f"status={result.status.value} error={result.error.code}")
        return 1

    stage_directory = _REPO_ROOT / "artifacts" / "runs" / request.run_id
    cached_result_path = stage_directory / "workbench_result.json"

    if cached_result_path.is_file():
        with open(cached_result_path) as f:
            cached = result_from_dict(json.load(f))
        replayed_result = dataclasses.replace(cached, replayed=True)
        _write(output_path, result_to_dict(replayed_result))
        print(f"status={replayed_result.status.value} (replayed run_id={request.run_id})")
        return 0 if replayed_result.status is WorkbenchRunStatus.SUCCEEDED else 1

    if request.contract_version != WORKBENCH_HARNESS_CONTRACT_VERSION:
        result = _rejection(
            run_id=request.run_id,
            code=WorkbenchRunErrorCode.CONTRACT_VERSION_MISMATCH,
            message=(
                f"Expected contract_version {WORKBENCH_HARNESS_CONTRACT_VERSION!r}, "
                f"got {request.contract_version!r}."
            ),
        )
    elif request.requested_entry_stage != SUPPORTED_ENTRY_STAGE:
        result = _rejection(
            run_id=request.run_id,
            code=WorkbenchRunErrorCode.UNSUPPORTED_ENTRY_STAGE,
            message=(
                f"requested_entry_stage {request.requested_entry_stage!r} is not supported; "
                f"only {SUPPORTED_ENTRY_STAGE!r} is implemented."
            ),
        )
    else:
        result = _execute(request, stage_directory=stage_directory, warnings=[])

    _write(cached_result_path, result_to_dict(result))
    _write(output_path, result_to_dict(result))

    print(f"status={result.status.value}")
    if result.error is not None:
        print(f"  error: {result.error.code} - {result.error.message}")
    for warning in result.warnings:
        print(f"  warning: {warning}")
    return 0 if result.status is WorkbenchRunStatus.SUCCEEDED else 1


if __name__ == "__main__":
    raise SystemExit(main())
