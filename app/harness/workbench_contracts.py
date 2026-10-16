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
    #: Human-review/resume increment: ``app.harness.hierarchical_recursion
    #: .resume_hierarchical_recursive_modularization`` raised
    #: ``HierarchicalRecursionCheckpointError`` -- a malformed, version-mismatched/stale, or
    #: decision-incomplete checkpoint, passed through as this error's own ``message`` verbatim.
    CHECKPOINT_REJECTED = "CHECKPOINT_REJECTED"


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


#: Automatic Hierarchical Recursive Modularization increment -- this *second*, genuinely
#: separate contract's own version. Unrelated to ``WORKBENCH_HARNESS_CONTRACT_VERSION`` above
#: (that one names the fixed five-agent FULL_PIPELINE workflow; this one names a hierarchical
#: modularization-refinement search against a model Agent 2 already assembled) and unrelated
#: to ``app.harness.version.HIERARCHICAL_RECURSION_POLICY_VERSION`` (the underlying
#: orchestration policy this contract wraps, never re-exposed or re-derived here).
WORKBENCH_HIERARCHICAL_CONTRACT_VERSION = "workbench-hierarchical-v1"


@dataclass(frozen=True, slots=True)
class WorkbenchHierarchicalInvocationRequest:
    """What the Workbench sends to ask the harness to run one hierarchical recursive
    modularization search (``app.harness.hierarchical_recursion
    .run_hierarchical_recursive_modularization``).

    ``criteria_weights``/``search_policy``/``calibration_selection_policy``/
    ``flat_orchestration_policy``/``recursion_policy`` are plain dicts, forwarded unread and
    unparsed to the underlying orchestration call -- exactly the same "the Workbench need not
    understand an agent's own request shape" convention
    ``WorkbenchInvocationRequest.input_artifact_references`` already uses for Agent 4's/Agent
    5's own request files. ``functional_evaluation_selection_policy`` is optional (``None``
    reproduces this harness's own identical "zero functional-evaluation decisions" default).

    ``input_artifact_references`` recognizes the identical ``"stage1_synthetic_source"`` key
    ``WorkbenchInvocationRequest`` already does (test/dev only); exactly one of
    ``agent1_organism_id`` or that key must be set, mirroring the FULL_PIPELINE contract's own
    identical requirement.

    **No calibration dataset provider.** This contract has no analog of a Stage4/Stage5 request
    file: the canonical entrypoint always uses a calibration request provider that returns no
    dataset, so every ``CALIBRATE`` decision resolves as ``NO_DATASET_AVAILABLE`` -- a disclosed
    scope limit (deciding what counts as a usable calibration dataset for an arbitrary candidate
    module is Agent 5's own future job, out of scope for this increment), never a silent
    fabrication.
    """

    contract_version: str
    run_id: str
    project_id: str
    subproject_id: str
    criteria_weights: dict
    search_policy: dict
    calibration_selection_policy: dict
    flat_orchestration_policy: dict
    recursion_policy: dict
    functional_evaluation_selection_policy: dict | None = None
    model_id: str | None = None
    agent1_organism_id: str | None = None
    input_artifact_references: dict[str, str] = field(default_factory=dict)
    exclude_single_module_from_ranking: bool = True
    apply_resolution_correction: bool = False
    correlation_id: str | None = None
    notes: str | None = None
    submitted_at: str | None = None


@dataclass(frozen=True, slots=True)
class WorkbenchHierarchyNodeSummary:
    """One ``app.harness.hierarchical_recursion.types.HierarchyNodeRecord``, reshaped into the
    Workbench's own plain, JSON-ready contract -- every field read verbatim, never re-derived or
    reinterpreted. The per-run policy/weight fields (``criteria_weights``, etc.) are
    deliberately not repeated per node here: they are identical across every node of one run
    and already recorded once on ``WorkbenchHierarchicalInvocationRequest`` itself."""

    node_id: str
    depth: int
    parent_modularization_id: str | None
    parent_module_id: str | None
    child_submodel_id: str | None
    child_modularization_id: str | None
    child_module_ids: tuple[str, ...]
    accepted: bool
    reason: str
    baseline_score: str | None
    child_score: str | None
    branch_stopping_reason: str | None
    recursive_search_stopping_reason: str
    recursive_search_rounds: int
    recursive_search_policy_version: str


@dataclass(frozen=True, slots=True)
class WorkbenchHierarchicalRunResult:
    """What the harness reports back for one ``WorkbenchHierarchicalInvocationRequest`` (or,
    human-review/resume increment, one ``WorkbenchHierarchicalResumeRequest`` -- the two share
    this identical result shape) -- the full node set (never truncated: the Workbench is
    expected to persist every one as its own first-class, queryable record, not just this
    summary blob)."""

    contract_version: str
    run_id: str
    status: WorkbenchRunStatus
    root_model_id: str | None
    nodes: tuple[WorkbenchHierarchyNodeSummary, ...]
    total_nodes_created: int
    total_functional_evaluations_used: int
    total_calibration_runs_used: int
    requires_user_review: bool
    pending_review_modules: tuple[dict, ...]
    recursion_policy_version: str
    started_at: str | None
    completed_at: str | None
    error: WorkbenchRunError | None
    summary: str
    warnings: tuple[str, ...] = ()
    replayed: bool = False
    #: Human-review/resume increment: the harness's own, verbatim-opaque
    #: ``app.harness.hierarchical_recursion.serialize_checkpoint(...)`` dict -- populated only
    #: when ``requires_user_review`` is ``True``. The Workbench stores this exactly as received
    #: (never reinterprets its own internal shape) and passes it back, unchanged, as
    #: ``WorkbenchHierarchicalResumeRequest.checkpoint`` to resume this run later.
    checkpoint: dict | None = None


def hierarchical_request_from_dict(data: dict) -> WorkbenchHierarchicalInvocationRequest:
    """Parse a plain dict into a ``WorkbenchHierarchicalInvocationRequest``. Raises
    ``KeyError``/``TypeError`` on a malformed request -- the canonical entrypoint catches these
    and reports ``WorkbenchRunErrorCode.MALFORMED_REQUEST``, never a traceback."""
    return WorkbenchHierarchicalInvocationRequest(
        contract_version=data["contract_version"],
        run_id=data["run_id"],
        project_id=data["project_id"],
        subproject_id=data["subproject_id"],
        criteria_weights=dict(data["criteria_weights"]),
        search_policy=dict(data["search_policy"]),
        calibration_selection_policy=dict(data["calibration_selection_policy"]),
        flat_orchestration_policy=dict(data["flat_orchestration_policy"]),
        recursion_policy=dict(data["recursion_policy"]),
        functional_evaluation_selection_policy=(
            dict(data["functional_evaluation_selection_policy"])
            if data.get("functional_evaluation_selection_policy") is not None
            else None
        ),
        model_id=data.get("model_id"),
        agent1_organism_id=data.get("agent1_organism_id"),
        input_artifact_references=dict(data.get("input_artifact_references") or {}),
        exclude_single_module_from_ranking=bool(
            data.get("exclude_single_module_from_ranking", True)
        ),
        apply_resolution_correction=bool(data.get("apply_resolution_correction", False)),
        correlation_id=data.get("correlation_id"),
        notes=data.get("notes"),
        submitted_at=data.get("submitted_at"),
    )


def hierarchical_result_to_dict(result: WorkbenchHierarchicalRunResult) -> dict:
    """Serialize a ``WorkbenchHierarchicalRunResult`` to a plain, JSON-ready dict."""
    return {
        "contract_version": result.contract_version,
        "run_id": result.run_id,
        "status": result.status.value,
        "root_model_id": result.root_model_id,
        "nodes": [
            {
                "node_id": n.node_id,
                "depth": n.depth,
                "parent_modularization_id": n.parent_modularization_id,
                "parent_module_id": n.parent_module_id,
                "child_submodel_id": n.child_submodel_id,
                "child_modularization_id": n.child_modularization_id,
                "child_module_ids": list(n.child_module_ids),
                "accepted": n.accepted,
                "reason": n.reason,
                "baseline_score": n.baseline_score,
                "child_score": n.child_score,
                "branch_stopping_reason": n.branch_stopping_reason,
                "recursive_search_stopping_reason": n.recursive_search_stopping_reason,
                "recursive_search_rounds": n.recursive_search_rounds,
                "recursive_search_policy_version": n.recursive_search_policy_version,
            }
            for n in result.nodes
        ],
        "total_nodes_created": result.total_nodes_created,
        "total_functional_evaluations_used": result.total_functional_evaluations_used,
        "total_calibration_runs_used": result.total_calibration_runs_used,
        "requires_user_review": result.requires_user_review,
        "pending_review_modules": [dict(m) for m in result.pending_review_modules],
        "recursion_policy_version": result.recursion_policy_version,
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
        "checkpoint": result.checkpoint,
    }


def hierarchical_result_from_dict(data: dict) -> WorkbenchHierarchicalRunResult:
    """The inverse of ``hierarchical_result_to_dict`` -- used to load a cached result for
    replay."""
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
    return WorkbenchHierarchicalRunResult(
        contract_version=data["contract_version"],
        run_id=data["run_id"],
        status=WorkbenchRunStatus(data["status"]),
        root_model_id=data.get("root_model_id"),
        nodes=tuple(
            WorkbenchHierarchyNodeSummary(
                node_id=n["node_id"],
                depth=n["depth"],
                parent_modularization_id=n.get("parent_modularization_id"),
                parent_module_id=n.get("parent_module_id"),
                child_submodel_id=n.get("child_submodel_id"),
                child_modularization_id=n.get("child_modularization_id"),
                child_module_ids=tuple(n.get("child_module_ids") or ()),
                accepted=bool(n["accepted"]),
                reason=n["reason"],
                baseline_score=n.get("baseline_score"),
                child_score=n.get("child_score"),
                branch_stopping_reason=n.get("branch_stopping_reason"),
                recursive_search_stopping_reason=n["recursive_search_stopping_reason"],
                recursive_search_rounds=n["recursive_search_rounds"],
                recursive_search_policy_version=n["recursive_search_policy_version"],
            )
            for n in data.get("nodes", ())
        ),
        total_nodes_created=data.get("total_nodes_created", 0),
        total_functional_evaluations_used=data.get("total_functional_evaluations_used", 0),
        total_calibration_runs_used=data.get("total_calibration_runs_used", 0),
        requires_user_review=bool(data.get("requires_user_review", False)),
        pending_review_modules=tuple(dict(m) for m in data.get("pending_review_modules", ())),
        recursion_policy_version=data.get("recursion_policy_version", ""),
        started_at=data.get("started_at"),
        completed_at=data.get("completed_at"),
        error=error,
        summary=data.get("summary", ""),
        warnings=tuple(data.get("warnings", ())),
        replayed=bool(data.get("replayed", False)),
        checkpoint=data.get("checkpoint"),
    )


#: Human-review/resume increment -- a second, genuinely separate contract from
#: ``WORKBENCH_HIERARCHICAL_CONTRACT_VERSION`` (that one names the *initial* invocation; this
#: one names resuming a paused run). Deliberately its own version: a Workbench build that only
#: knows the initial-invocation contract should never be able to accidentally construct a
#: resume request that looks valid.
WORKBENCH_HIERARCHICAL_RESUME_CONTRACT_VERSION = "workbench-hierarchical-resume-v1"


@dataclass(frozen=True, slots=True)
class WorkbenchHierarchicalResumeRequest:
    """What the Workbench sends to resume one paused hierarchical-recursion run
    (``app.harness.hierarchical_recursion.resume_hierarchical_recursive_modularization``).

    ``checkpoint`` is the Workbench's own stored copy of a prior
    ``WorkbenchHierarchicalRunResult.checkpoint`` -- passed back here verbatim, never
    reconstructed or edited; the canonical resume entrypoint deserializes it with
    ``app.harness.hierarchical_recursion.deserialize_checkpoint`` and validates its own
    version compatibility exactly as that function already does for any other caller.
    ``decisions`` maps each pending entry's own ``pending_id`` (as the paused run's own
    ``pending_review_modules`` reported it) to ``"APPROVE"``/``"REJECT"``.
    """

    contract_version: str
    run_id: str
    checkpoint: dict
    decisions: dict[str, str]
    correlation_id: str | None = None
    notes: str | None = None
    submitted_at: str | None = None


def hierarchical_resume_request_to_dict(request: WorkbenchHierarchicalResumeRequest) -> dict:
    """Serialize a ``WorkbenchHierarchicalResumeRequest`` to a plain, JSON-ready dict."""
    return {
        "contract_version": request.contract_version,
        "run_id": request.run_id,
        "checkpoint": request.checkpoint,
        "decisions": dict(request.decisions),
        "correlation_id": request.correlation_id,
        "notes": request.notes,
        "submitted_at": request.submitted_at,
    }


def hierarchical_resume_request_from_dict(data: dict) -> WorkbenchHierarchicalResumeRequest:
    """Parse a plain dict into a ``WorkbenchHierarchicalResumeRequest``. Raises
    ``KeyError``/``TypeError`` on a malformed request -- the canonical resume entrypoint catches
    these and reports ``WorkbenchRunErrorCode.MALFORMED_REQUEST``, never a traceback."""
    return WorkbenchHierarchicalResumeRequest(
        contract_version=data["contract_version"],
        run_id=data["run_id"],
        checkpoint=dict(data["checkpoint"]),
        decisions=dict(data["decisions"]),
        correlation_id=data.get("correlation_id"),
        notes=data.get("notes"),
        submitted_at=data.get("submitted_at"),
    )


__all__ = [
    "SUPPORTED_ENTRY_STAGE",
    "WORKBENCH_HARNESS_CONTRACT_VERSION",
    "WORKBENCH_HIERARCHICAL_CONTRACT_VERSION",
    "WORKBENCH_HIERARCHICAL_RESUME_CONTRACT_VERSION",
    "WorkbenchHierarchicalInvocationRequest",
    "WorkbenchHierarchicalResumeRequest",
    "WorkbenchHierarchicalRunResult",
    "WorkbenchHierarchyNodeSummary",
    "WorkbenchInvocationRequest",
    "WorkbenchRunError",
    "WorkbenchRunErrorCode",
    "WorkbenchRunResult",
    "WorkbenchRunStatus",
    "hierarchical_request_from_dict",
    "hierarchical_result_from_dict",
    "hierarchical_result_to_dict",
    "hierarchical_resume_request_from_dict",
    "hierarchical_resume_request_to_dict",
    "request_from_dict",
    "result_from_dict",
    "result_to_dict",
]
