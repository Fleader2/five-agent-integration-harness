"""The Workbench <-> Harness invocation/result contract.

A plain, frozen, JSON-friendly dataclass pair, exactly like every other contract type in this
project's family (``app.harness.types``) -- the harness has no runtime dependency on
``mechanistic-modeling-workbench`` and never will; this module is this repository's own,
independently-maintained copy of the shape the Workbench's own
``app.contracts.harness`` module also defines. A mismatch between the two is exactly what
``contract_version`` below exists to catch, the same way every other inter-repository boundary
in this project already works.

This module defines the contract shape only. ``scripts/run_workbench_request.py`` is the
canonical entrypoint that actually consumes a ``WorkbenchInvocationRequest`` and produces a
``WorkbenchRunResult`` -- see that script's own module docstring for the full execution
semantics (idempotent replay, the one supported ``requested_entry_stage``, and the disclosed
``ModelBuildRequest`` gap).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

#: This contract's own version -- bumped only when a field in this module's own dataclasses
#: changes. Never conflated with ``app.harness.version.HARNESS_CONTRACT_VERSION`` (the harness's
#: own internal five-agent workflow report contract) or with any agent's own scientific
#: contract version.
WORKBENCH_HARNESS_CONTRACT_VERSION = "workbench-harness-v1"

#: The only ``requested_entry_stage`` value the canonical entrypoint currently supports. The
#: underlying ``app.harness.pipeline.run_workflow`` always runs the full, fixed
#: Agent1->2->3->4->5 sequence -- there is no partial/entry-stage execution mode anywhere in
#: this harness today. A request naming any other value is rejected deterministically
#: (``WorkbenchRunErrorCode.UNSUPPORTED_ENTRY_STAGE``), never silently coerced to this one.
SUPPORTED_ENTRY_STAGE = "FULL_PIPELINE"


class WorkbenchRunStatus(StrEnum):
    """The outcome of one Workbench-invoked harness run."""

    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    #: Defined for forward compatibility; never produced by the current canonical entrypoint --
    #: the harness's own subprocess chain runs synchronously to completion or failure, with no
    #: cancellation mechanism.
    CANCELLED = "CANCELLED"


class WorkbenchRunErrorCode(StrEnum):
    """Closed, deterministic failure reasons the canonical entrypoint itself can report --
    distinct from an individual agent stage's own failure, which is instead carried in
    ``WorkbenchRunResult.error.stage_name``/``message`` with ``code=AGENT_STAGE_FAILED`` (the
    harness's own ``WorkflowStatus`` value, passed through verbatim).
    """

    MALFORMED_REQUEST = "MALFORMED_REQUEST"
    CONTRACT_VERSION_MISMATCH = "CONTRACT_VERSION_MISMATCH"
    UNSUPPORTED_ENTRY_STAGE = "UNSUPPORTED_ENTRY_STAGE"
    INVALID_STAGE1_INPUT = "INVALID_STAGE1_INPUT"
    MISSING_INPUT_ARTIFACT = "MISSING_INPUT_ARTIFACT"
    #: One of ``app.harness.types.WorkflowStatus``'s own failure values
    #: (``CONTRACT_MISMATCH``/``AGENT_STAGE_FAILED``/``INVALID_ARTIFACT``/``BLOCKED``), passed
    #: through verbatim as the error code when the underlying workflow itself failed.
    WORKFLOW_FAILED = "WORKFLOW_FAILED"


@dataclass(frozen=True, slots=True)
class WorkbenchInvocationRequest:
    """What the Workbench sends to ask the harness to run the five-agent workflow.

    ``input_artifact_references`` is a plain ``{name: path}`` mapping, read directly from disk
    by the canonical entrypoint -- never a new scientific contract. Recognized keys:
    ``"stage4_request"``/``"stage5_request"`` (Agent 4's/Agent 5's own request JSON, required),
    and ``"stage1_synthetic_source"`` (test/dev only -- a hand-authored Agent 1 view JSON, used
    in place of a real ``agent1_organism_id`` database query).

    ``model_build_request_id``, when supplied, is accepted and recorded, but **not yet acted on**
    by the canonical entrypoint: Agent 2 has no mechanism to consume a scoped build request (see
    the architecture audit and ``docs/07_workbench_harness_contract.md``'s own disclosed gap) --
    only a disclosed warning is produced, never a silent no-op.
    """

    contract_version: str
    run_id: str
    project_id: str
    subproject_id: str
    task_type: str
    requested_entry_stage: str
    model_id: str | None = None
    model_build_request_id: str | None = None
    agent1_organism_id: str | None = None
    input_artifact_references: dict[str, str] = field(default_factory=dict)
    correlation_id: str | None = None
    notes: str | None = None
    submitted_at: str | None = None


@dataclass(frozen=True, slots=True)
class WorkbenchRunError:
    """Structured error information for a failed/rejected run."""

    code: str
    message: str
    stage_name: str | None = None


@dataclass(frozen=True, slots=True)
class WorkbenchRunResult:
    """What the harness reports back for one ``WorkbenchInvocationRequest``."""

    contract_version: str
    run_id: str
    status: WorkbenchRunStatus
    stages_executed: tuple[str, ...]
    output_artifact_references: dict[str, str]
    model_artifact_reference: str | None
    agent_contract_versions: dict[str, str | None]
    started_at: str | None
    completed_at: str | None
    error: WorkbenchRunError | None
    summary: str
    warnings: tuple[str, ...] = ()
    #: ``True`` when this response is a replay of an already-completed run (identified by
    #: ``run_id``) rather than a fresh execution -- see the canonical entrypoint's own
    #: idempotency section.
    replayed: bool = False


def request_from_dict(data: dict) -> WorkbenchInvocationRequest:
    """Parse a plain dict (as read from a JSON file) into a ``WorkbenchInvocationRequest``.

    Raises ``KeyError``/``TypeError`` on a malformed request -- the canonical entrypoint catches
    these and reports ``WorkbenchRunErrorCode.MALFORMED_REQUEST``, never a traceback.
    """
    return WorkbenchInvocationRequest(
        contract_version=data["contract_version"],
        run_id=data["run_id"],
        project_id=data["project_id"],
        subproject_id=data["subproject_id"],
        task_type=data["task_type"],
        requested_entry_stage=data["requested_entry_stage"],
        model_id=data.get("model_id"),
        model_build_request_id=data.get("model_build_request_id"),
        agent1_organism_id=data.get("agent1_organism_id"),
        input_artifact_references=dict(data.get("input_artifact_references") or {}),
        correlation_id=data.get("correlation_id"),
        notes=data.get("notes"),
        submitted_at=data.get("submitted_at"),
    )


def result_to_dict(result: WorkbenchRunResult) -> dict:
    """Serialize a ``WorkbenchRunResult`` to a plain, JSON-ready dict."""
    return {
        "contract_version": result.contract_version,
        "run_id": result.run_id,
        "status": result.status.value,
        "stages_executed": list(result.stages_executed),
        "output_artifact_references": dict(result.output_artifact_references),
        "model_artifact_reference": result.model_artifact_reference,
        "agent_contract_versions": dict(result.agent_contract_versions),
        "started_at": result.started_at,
        "completed_at": result.completed_at,
        "error": (
            None
            if result.error is None
            else {
                "code": result.error.code,
                "message": result.error.message,
                "stage_name": result.error.stage_name,
            }
        ),
        "summary": result.summary,
        "warnings": list(result.warnings),
        "replayed": result.replayed,
    }


def result_from_dict(data: dict) -> WorkbenchRunResult:
    """The inverse of ``result_to_dict`` -- used to load a cached result for replay."""
    error_data = data.get("error")
    error = (
        None
        if error_data is None
        else WorkbenchRunError(
            code=error_data["code"],
            message=error_data["message"],
            stage_name=error_data.get("stage_name"),
        )
    )
    return WorkbenchRunResult(
        contract_version=data["contract_version"],
        run_id=data["run_id"],
        status=WorkbenchRunStatus(data["status"]),
        stages_executed=tuple(data.get("stages_executed", ())),
        output_artifact_references=dict(data.get("output_artifact_references") or {}),
        model_artifact_reference=data.get("model_artifact_reference"),
        agent_contract_versions=dict(data.get("agent_contract_versions") or {}),
        started_at=data.get("started_at"),
        completed_at=data.get("completed_at"),
        error=error,
        summary=data.get("summary", ""),
        warnings=tuple(data.get("warnings", ())),
        replayed=bool(data.get("replayed", False)),
    )


__all__ = [
    "SUPPORTED_ENTRY_STAGE",
    "WORKBENCH_HARNESS_CONTRACT_VERSION",
    "WorkbenchInvocationRequest",
    "WorkbenchRunError",
    "WorkbenchRunErrorCode",
    "WorkbenchRunResult",
    "WorkbenchRunStatus",
    "request_from_dict",
    "result_from_dict",
    "result_to_dict",
]
