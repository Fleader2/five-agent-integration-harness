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
    #: Executable-Module Materialization increment:
    #: ``app.harness.module_simulation.ModuleSimulationWorkflowError`` -- a malformed request,
    #: an Agent 2/Agent 3 subprocess failure, or (most commonly) the target module having no
    #: eligible standalone executable artifact -- a genuine, disclosed "this module cannot be
    #: simulated" outcome, never silently accepted.
    MODULE_SIMULATION_FAILED = "MODULE_SIMULATION_FAILED"
    #: Boundary-Condition Semantics increment:
    #: ``app.harness.module_boundary_derivation.ModuleBoundaryDerivationWorkflowError`` -- a
    #: malformed request or an Agent 2 subprocess failure. Never produced for an empty
    #: candidate list (a module with no cross-boundary species is a genuine, disclosed
    #: outcome, not a failure).
    MODULE_BOUNDARY_DERIVATION_FAILED = "MODULE_BOUNDARY_DERIVATION_FAILED"
    #: Module-Level Agent4 Calibration increment:
    #: ``app.harness.module_calibration_execution.ModuleCalibrationExecutionWorkflowError`` --
    #: a malformed request, a calibration target/observation naming a parameter/species the
    #: materialized module does not have, the target module having no eligible standalone
    #: executable artifact, or an Agent 2/Agent 3/Agent 4 subprocess failure. Never produced
    #: for a real, disclosed Agent 4 calibration outcome (SUCCESS/PARTIAL_SUCCESS/
    #: OPTIMIZATION_FAILED/etc. are all carried through in the result's own ``agent4_report``).
    MODULE_CALIBRATION_EXECUTION_FAILED = "MODULE_CALIBRATION_EXECUTION_FAILED"
    #: Module-Level Agent5 Validation and Experimental Design increment:
    #: ``app.harness.module_validation_execution.ModuleValidationExecutionWorkflowError`` -- a
    #: malformed request, a validation observation naming a species the materialized module
    #: does not have, the target module having no eligible standalone executable artifact, or
    #: an Agent 2/Agent 5 subprocess failure. Never produced for a real, disclosed Agent 5
    #: validation outcome (SUCCESS/VALIDATION_FAILED/OVERFIT_WARNING/etc. are all carried
    #: through in the result's own ``agent5_report``).
    MODULE_VALIDATION_EXECUTION_FAILED = "MODULE_VALIDATION_EXECUTION_FAILED"
    #: Module-Set Edited-Module Materialization increment:
    #: ``app.harness.module_rematerialization.ModuleRematerializationWorkflowError`` -- a
    #: malformed request, an unknown reaction id, a selection with zero reactions, or an Agent
    #: 2 subprocess failure. Never produced for a module that materializes correctly but has
    #: no eligible standalone executable artifact yet (a genuine, disclosed "materialized, not
    #: yet simulatable" outcome -- carried in the result's own ``readiness_blocked_reason``,
    #: never an error).
    MODULE_REMATERIALIZATION_FAILED = "MODULE_REMATERIALIZATION_FAILED"
    #: Module-Set Edited-Module Materialization increment, Phase B:
    #: ``app.harness.module_set_simulation.ModuleSetSimulationWorkflowError`` -- a malformed
    #: request, no resolved boundary treatments supplied, a rebuilt module with no eligible
    #: standalone executable artifact, or an Agent 2/Agent 3 subprocess failure. Never produced
    #: for a real, disclosed Agent 3 simulation outcome (carried through verbatim in the
    #: result's own ``agent3_report``).
    MODULE_SET_SIMULATION_FAILED = "MODULE_SET_SIMULATION_FAILED"
    #: Whole-Model Experimental-Scenario Evaluation increment:
    #: ``app.harness.model_scenario_evaluation.ModelScenarioEvaluationWorkflowError`` -- a
    #: malformed request or an Agent 3 subprocess crash/timeout/malformed output. Never
    #: produced for a real, disclosed Agent 3 evaluation outcome (``MODEL_LOAD_FAILED``/
    #: ``INVALID_REQUEST``/``SIMULATION_FAILED``/``NUMERICAL_INSTABILITY`` are all carried
    #: through verbatim in the result's own ``evaluation_status``/``validation_errors``).
    MODEL_SCENARIO_EVALUATION_FAILED = "MODEL_SCENARIO_EVALUATION_FAILED"
    #: Whole-Model Antimony Import increment:
    #: ``app.harness.model_antimony_import.ModelAntimonyImportWorkflowError`` -- a malformed
    #: request or an Agent 2 subprocess crash/timeout/malformed output. Never produced for a
    #: real, disclosed Agent 2 import outcome (``MALFORMED``/``UNSUPPORTED_CONSTRUCT``/
    #: ``AMBIGUOUS_MODULE`` are all carried through verbatim in the result's own
    #: ``import_error_kind``/``import_message``).
    MODEL_ANTIMONY_IMPORT_FAILED = "MODEL_ANTIMONY_IMPORT_FAILED"


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
    #: Executable-Module Materialization increment: the exact payload that was used to
    #: materialize *this* node's own submodel (``None`` for the root node and for a node never
    #: actually searched) -- see ``HierarchyNodeRecord.attach_payload``'s own docstring. The
    #: Workbench stores this verbatim and later passes it back, unchanged, to request an Agent
    #: 3 simulation against exactly this module's own executable artifact.
    attach_payload: dict | None = None


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
                "attach_payload": n.attach_payload,
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
                attach_payload=n.get("attach_payload"),
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


#: Executable-Module Materialization increment -- a third, genuinely separate contract from
#: both the initial hierarchical-recursion invocation and its resume: this one names simulating
#: one already-accepted hierarchy module (not the whole root model) through Agent 2 then Agent
#: 3. Deliberately its own version.
WORKBENCH_MODULE_SIMULATION_CONTRACT_VERSION = "workbench-module-simulation-v1"


@dataclass(frozen=True, slots=True)
class WorkbenchModuleSimulationRequest:
    """What the Workbench sends to ask the harness to simulate one accepted hierarchy module.

    ``attach_payload`` is the Workbench's own stored, verbatim-opaque copy of a prior
    ``WorkbenchHierarchyNodeSummary.attach_payload`` -- passed back here unchanged, never
    reconstructed or edited; it is this one payload (never a multi-level chain) that lets the
    canonical entrypoint re-materialize exactly this module's own standalone executable
    artifact from a freshly-rebuilt root model. ``module_id`` names the specific module within
    it to simulate. Exactly one of ``agent1_organism_id`` or
    ``input_artifact_references["stage1_synthetic_source"]`` must be set, mirroring every other
    contract in this family's identical requirement.
    """

    contract_version: str
    run_id: str
    project_id: str
    subproject_id: str
    attach_payload: dict
    module_id: str
    agent1_organism_id: str | None = None
    input_artifact_references: dict[str, str] = field(default_factory=dict)
    correlation_id: str | None = None
    notes: str | None = None
    submitted_at: str | None = None


@dataclass(frozen=True, slots=True)
class WorkbenchModuleSimulationResult:
    """What the harness reports back for one ``WorkbenchModuleSimulationRequest``."""

    contract_version: str
    run_id: str
    status: WorkbenchRunStatus
    module_id: str | None
    modularization_id: str | None
    #: ``{"model_id", "species_count", "reaction_count", "parameter_count"}`` -- enough to
    #: confirm the *module's own* filtered artifact (not the root model's) was what Agent 3
    #: actually simulated, without the Workbench needing to parse the full handoff.
    module_handoff_summary: dict | None
    #: Agent 3's own full ``Agent3Report`` dict, read verbatim -- never reshaped or
    #: reinterpreted here.
    agent3_report: dict | None
    started_at: str | None
    completed_at: str | None
    error: WorkbenchRunError | None
    summary: str
    warnings: tuple[str, ...] = ()
    replayed: bool = False


def module_simulation_request_to_dict(request: WorkbenchModuleSimulationRequest) -> dict:
    """Serialize a ``WorkbenchModuleSimulationRequest`` to a plain, JSON-ready dict."""
    return {
        "contract_version": request.contract_version,
        "run_id": request.run_id,
        "project_id": request.project_id,
        "subproject_id": request.subproject_id,
        "attach_payload": dict(request.attach_payload),
        "module_id": request.module_id,
        "agent1_organism_id": request.agent1_organism_id,
        "input_artifact_references": dict(request.input_artifact_references),
        "correlation_id": request.correlation_id,
        "notes": request.notes,
        "submitted_at": request.submitted_at,
    }


def module_simulation_request_from_dict(data: dict) -> WorkbenchModuleSimulationRequest:
    """Parse a plain dict into a ``WorkbenchModuleSimulationRequest``. Raises
    ``KeyError``/``TypeError`` on a malformed request -- the canonical entrypoint catches these
    and reports ``WorkbenchRunErrorCode.MALFORMED_REQUEST``, never a traceback."""
    return WorkbenchModuleSimulationRequest(
        contract_version=data["contract_version"],
        run_id=data["run_id"],
        project_id=data["project_id"],
        subproject_id=data["subproject_id"],
        attach_payload=dict(data["attach_payload"]),
        module_id=data["module_id"],
        agent1_organism_id=data.get("agent1_organism_id"),
        input_artifact_references=dict(data.get("input_artifact_references") or {}),
        correlation_id=data.get("correlation_id"),
        notes=data.get("notes"),
        submitted_at=data.get("submitted_at"),
    )


def module_simulation_result_to_dict(result: WorkbenchModuleSimulationResult) -> dict:
    """Serialize a ``WorkbenchModuleSimulationResult`` to a plain, JSON-ready dict."""
    return {
        "contract_version": result.contract_version,
        "run_id": result.run_id,
        "status": result.status.value,
        "module_id": result.module_id,
        "modularization_id": result.modularization_id,
        "module_handoff_summary": result.module_handoff_summary,
        "agent3_report": result.agent3_report,
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


def module_simulation_result_from_dict(data: dict) -> WorkbenchModuleSimulationResult:
    """The inverse of ``module_simulation_result_to_dict`` -- used to load a cached result for
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
    return WorkbenchModuleSimulationResult(
        contract_version=data["contract_version"],
        run_id=data["run_id"],
        status=WorkbenchRunStatus(data["status"]),
        module_id=data.get("module_id"),
        modularization_id=data.get("modularization_id"),
        module_handoff_summary=data.get("module_handoff_summary"),
        agent3_report=data.get("agent3_report"),
        started_at=data.get("started_at"),
        completed_at=data.get("completed_at"),
        error=error,
        summary=data.get("summary", ""),
        warnings=tuple(data.get("warnings", ())),
        replayed=bool(data.get("replayed", False)),
    )


#: Boundary-Condition Semantics increment -- a fourth, genuinely separate contract: this one
#: names deriving *candidate* boundary species for one already-accepted hierarchy module from
#: Agent 2's own reaction-participant topology -- never a treatment decision, never a
#: simulation. Deliberately its own version.
WORKBENCH_MODULE_BOUNDARY_DERIVATION_CONTRACT_VERSION = "workbench-module-boundary-derivation-v1"


@dataclass(frozen=True, slots=True)
class WorkbenchModuleBoundaryDerivationRequest:
    """What the Workbench sends to ask the harness to derive candidate boundary species for one
    accepted hierarchy module.

    ``attach_payload`` is the Workbench's own stored, verbatim-opaque copy of a prior
    ``WorkbenchHierarchyNodeSummary.attach_payload`` -- passed back here unchanged, mirroring
    ``WorkbenchModuleSimulationRequest``'s own identical field exactly. ``module_id`` names the
    specific module within it to derive boundary candidates for.
    """

    contract_version: str
    run_id: str
    project_id: str
    subproject_id: str
    attach_payload: dict
    module_id: str
    agent1_organism_id: str | None = None
    input_artifact_references: dict[str, str] = field(default_factory=dict)
    correlation_id: str | None = None
    notes: str | None = None
    submitted_at: str | None = None


@dataclass(frozen=True, slots=True)
class WorkbenchModuleBoundaryDerivationResult:
    """What the harness reports back for one ``WorkbenchModuleBoundaryDerivationRequest``."""

    contract_version: str
    run_id: str
    status: WorkbenchRunStatus
    module_id: str | None
    #: ``[{"species_id", "direction"}, ...]`` -- structural candidates only, never a treatment
    #: decision or a fabricated value.
    candidates: tuple[dict, ...]
    started_at: str | None
    completed_at: str | None
    error: WorkbenchRunError | None
    summary: str
    warnings: tuple[str, ...] = ()
    replayed: bool = False


def module_boundary_derivation_request_to_dict(
    request: WorkbenchModuleBoundaryDerivationRequest,
) -> dict:
    """Serialize a ``WorkbenchModuleBoundaryDerivationRequest`` to a plain, JSON-ready dict."""
    return {
        "contract_version": request.contract_version,
        "run_id": request.run_id,
        "project_id": request.project_id,
        "subproject_id": request.subproject_id,
        "attach_payload": dict(request.attach_payload),
        "module_id": request.module_id,
        "agent1_organism_id": request.agent1_organism_id,
        "input_artifact_references": dict(request.input_artifact_references),
        "correlation_id": request.correlation_id,
        "notes": request.notes,
        "submitted_at": request.submitted_at,
    }


def module_boundary_derivation_request_from_dict(
    data: dict,
) -> WorkbenchModuleBoundaryDerivationRequest:
    """Parse a plain dict into a ``WorkbenchModuleBoundaryDerivationRequest``. Raises
    ``KeyError``/``TypeError`` on a malformed request -- the canonical entrypoint catches these
    and reports ``WorkbenchRunErrorCode.MALFORMED_REQUEST``, never a traceback."""
    return WorkbenchModuleBoundaryDerivationRequest(
        contract_version=data["contract_version"],
        run_id=data["run_id"],
        project_id=data["project_id"],
        subproject_id=data["subproject_id"],
        attach_payload=dict(data["attach_payload"]),
        module_id=data["module_id"],
        agent1_organism_id=data.get("agent1_organism_id"),
        input_artifact_references=dict(data.get("input_artifact_references") or {}),
        correlation_id=data.get("correlation_id"),
        notes=data.get("notes"),
        submitted_at=data.get("submitted_at"),
    )


def module_boundary_derivation_result_to_dict(
    result: WorkbenchModuleBoundaryDerivationResult,
) -> dict:
    """Serialize a ``WorkbenchModuleBoundaryDerivationResult`` to a plain, JSON-ready dict."""
    return {
        "contract_version": result.contract_version,
        "run_id": result.run_id,
        "status": result.status.value,
        "module_id": result.module_id,
        "candidates": list(result.candidates),
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


def module_boundary_derivation_result_from_dict(
    data: dict,
) -> WorkbenchModuleBoundaryDerivationResult:
    """The inverse of ``module_boundary_derivation_result_to_dict`` -- used to load a cached
    result for replay."""
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
    return WorkbenchModuleBoundaryDerivationResult(
        contract_version=data["contract_version"],
        run_id=data["run_id"],
        status=WorkbenchRunStatus(data["status"]),
        module_id=data.get("module_id"),
        candidates=tuple(data.get("candidates", ())),
        started_at=data.get("started_at"),
        completed_at=data.get("completed_at"),
        error=error,
        summary=data.get("summary", ""),
        warnings=tuple(data.get("warnings", ())),
        replayed=bool(data.get("replayed", False)),
    )


#: Module-Set Edited-Module Materialization increment -- a genuinely separate contract: this
#: one names rebuilding one module's own executable content from a Workbench-supplied,
#: explicit REACTION-id selection (never a pre-existing, already-decided ``attach_payload``) --
#: correctly recomputing its full dependency closure through Agent 2's own, unmodified
#: ``materialize_submodel``, and (only once resolved boundary treatments are also supplied) an
#: executable module handoff. Deliberately its own version.
WORKBENCH_MODULE_REMATERIALIZATION_CONTRACT_VERSION = "workbench-module-rematerialization-v1"


@dataclass(frozen=True, slots=True)
class WorkbenchModuleRematerializationRequest:
    """What the Workbench sends to ask the harness to rebuild one module's own executable
    content from an explicit, possibly-edited reaction selection.

    ``attach_payload`` is the Workbench's own synthetic ``{"modularization_id", "module_ids",
    "memberships"}`` dict naming exactly one target module's own current reaction selection --
    REACTION-type memberships only; never species/parameters/rules/events/observables, which
    the harness's own Agent 2 call derives correctly. ``module_id`` names the target module
    within it. ``module_ports``, when given, are the scientist's own resolved boundary
    treatments for this exact selection (never carried forward from a different selection) --
    omit for a materialize-structure-only call.
    """

    contract_version: str
    run_id: str
    project_id: str
    subproject_id: str
    attach_payload: dict
    module_id: str
    module_ports: tuple[dict, ...] = ()
    agent1_organism_id: str | None = None
    input_artifact_references: dict[str, str] = field(default_factory=dict)
    correlation_id: str | None = None
    notes: str | None = None
    submitted_at: str | None = None


@dataclass(frozen=True, slots=True)
class WorkbenchModuleRematerializationResult:
    """What the harness reports back for one ``WorkbenchModuleRematerializationRequest``."""

    contract_version: str
    run_id: str
    status: WorkbenchRunStatus
    module_id: str | None
    #: The Agent 2 module-handoff dict (species/reactions/parameters/kinetic laws, as every
    #: other module-scoped workflow already produces) -- ``None`` unless ``module_ports`` made
    #: the rebuilt module genuinely executable.
    module_handoff: dict | None
    #: Set only when ``module_handoff`` is ``None`` -- why it isn't executable yet (e.g. no
    #: boundary treatments supplied), never a fabricated reason.
    readiness_blocked_reason: str | None
    #: ``{"parent_model_id", "parent_modularization_id", "parent_module_id",
    #: "submodel_modularization_id", "submodel_module_id", "retained_reaction_ids",
    #: "retained_species_ids", "retained_parameter_ids", "retained_compartment_ids",
    #: "explicit_enzyme_species_ids", "retained_rule_ids", "retained_event_ids",
    #: "retained_observable_ids", "materialization_policy_version"}`` -- exact traceability
    #: back to the parent model and the real closure this selection actually produced.
    lineage: dict | None
    #: ``[{"component_type", "component_id", "referenced_ids", "reason"}, ...]`` -- rule/event/
    #: observable exclusions, disclosed, never silently dropped.
    unresolved_dependencies: tuple[dict, ...] = ()
    started_at: str | None = None
    completed_at: str | None = None
    error: WorkbenchRunError | None = None
    summary: str = ""
    warnings: tuple[str, ...] = ()
    replayed: bool = False


def module_rematerialization_request_to_dict(
    request: WorkbenchModuleRematerializationRequest,
) -> dict:
    """Serialize a ``WorkbenchModuleRematerializationRequest`` to a plain, JSON-ready dict."""
    return {
        "contract_version": request.contract_version,
        "run_id": request.run_id,
        "project_id": request.project_id,
        "subproject_id": request.subproject_id,
        "attach_payload": dict(request.attach_payload),
        "module_id": request.module_id,
        "module_ports": list(request.module_ports),
        "agent1_organism_id": request.agent1_organism_id,
        "input_artifact_references": dict(request.input_artifact_references),
        "correlation_id": request.correlation_id,
        "notes": request.notes,
        "submitted_at": request.submitted_at,
    }


def module_rematerialization_request_from_dict(
    data: dict,
) -> WorkbenchModuleRematerializationRequest:
    """Parse a plain dict into a ``WorkbenchModuleRematerializationRequest``. Raises
    ``KeyError``/``TypeError`` on a malformed request -- the canonical entrypoint catches these
    and reports ``WorkbenchRunErrorCode.MALFORMED_REQUEST``, never a traceback."""
    return WorkbenchModuleRematerializationRequest(
        contract_version=data["contract_version"],
        run_id=data["run_id"],
        project_id=data["project_id"],
        subproject_id=data["subproject_id"],
        attach_payload=dict(data["attach_payload"]),
        module_id=data["module_id"],
        module_ports=tuple(data.get("module_ports") or ()),
        agent1_organism_id=data.get("agent1_organism_id"),
        input_artifact_references=dict(data.get("input_artifact_references") or {}),
        correlation_id=data.get("correlation_id"),
        notes=data.get("notes"),
        submitted_at=data.get("submitted_at"),
    )


def module_rematerialization_result_to_dict(result: WorkbenchModuleRematerializationResult) -> dict:
    """Serialize a ``WorkbenchModuleRematerializationResult`` to a plain, JSON-ready dict."""
    return {
        "contract_version": result.contract_version,
        "run_id": result.run_id,
        "status": result.status.value,
        "module_id": result.module_id,
        "module_handoff": result.module_handoff,
        "readiness_blocked_reason": result.readiness_blocked_reason,
        "lineage": result.lineage,
        "unresolved_dependencies": list(result.unresolved_dependencies),
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


def module_rematerialization_result_from_dict(
    data: dict,
) -> WorkbenchModuleRematerializationResult:
    """The inverse of ``module_rematerialization_result_to_dict`` -- used to load a cached
    result for replay."""
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
    return WorkbenchModuleRematerializationResult(
        contract_version=data["contract_version"],
        run_id=data["run_id"],
        status=WorkbenchRunStatus(data["status"]),
        module_id=data.get("module_id"),
        module_handoff=data.get("module_handoff"),
        readiness_blocked_reason=data.get("readiness_blocked_reason"),
        lineage=data.get("lineage"),
        unresolved_dependencies=tuple(data.get("unresolved_dependencies", ())),
        started_at=data.get("started_at"),
        completed_at=data.get("completed_at"),
        error=error,
        summary=data.get("summary", ""),
        warnings=tuple(data.get("warnings", ())),
        replayed=bool(data.get("replayed", False)),
    )


#: Module-Set Edited-Module Materialization increment, Phase B -- a genuinely separate
#: contract: this one names *simulating* a module-set member's own current reaction selection
#: and resolved boundary treatments (correct rebuild through
#: ``WorkbenchModuleRematerializationRequest``'s own mechanism, then unchanged Agent 3) --
#: never a pre-existing, already-decided ``attach_payload``. Deliberately its own version.
WORKBENCH_MODULE_SET_SIMULATION_CONTRACT_VERSION = "workbench-module-set-simulation-v1"


@dataclass(frozen=True, slots=True)
class WorkbenchModuleSetSimulationRequest:
    """What the Workbench sends to ask the harness to simulate one module-set member's own
    current, possibly-edited reaction selection.

    ``attach_payload``/``module_id`` are identical in shape to
    ``WorkbenchModuleRematerializationRequest``'s own fields. ``module_ports`` -- the
    scientist's own resolved boundary treatments for this exact selection -- is required here
    (never optional, unlike the rematerialization contract's own structure-only mode): this
    contract's entire purpose is producing a real Agent 3 simulation, never a materialize-only
    outcome.
    """

    contract_version: str
    run_id: str
    project_id: str
    subproject_id: str
    attach_payload: dict
    module_id: str
    module_ports: tuple[dict, ...]
    agent1_organism_id: str | None = None
    input_artifact_references: dict[str, str] = field(default_factory=dict)
    correlation_id: str | None = None
    notes: str | None = None
    submitted_at: str | None = None


@dataclass(frozen=True, slots=True)
class WorkbenchModuleSetSimulationResult:
    """What the harness reports back for one ``WorkbenchModuleSetSimulationRequest``."""

    contract_version: str
    run_id: str
    status: WorkbenchRunStatus
    module_id: str | None
    module_handoff_summary: dict | None
    #: Exact traceability for *this* simulation's own rebuilt module -- see
    #: ``WorkbenchModuleRematerializationResult.lineage``'s own shape.
    lineage: dict | None
    #: Agent 3's own full ``Agent3Report`` dict, read verbatim -- never reshaped here.
    agent3_report: dict | None
    started_at: str | None
    completed_at: str | None
    error: WorkbenchRunError | None
    summary: str
    warnings: tuple[str, ...] = ()
    replayed: bool = False


def module_set_simulation_request_to_dict(request: WorkbenchModuleSetSimulationRequest) -> dict:
    """Serialize a ``WorkbenchModuleSetSimulationRequest`` to a plain, JSON-ready dict."""
    return {
        "contract_version": request.contract_version,
        "run_id": request.run_id,
        "project_id": request.project_id,
        "subproject_id": request.subproject_id,
        "attach_payload": dict(request.attach_payload),
        "module_id": request.module_id,
        "module_ports": list(request.module_ports),
        "agent1_organism_id": request.agent1_organism_id,
        "input_artifact_references": dict(request.input_artifact_references),
        "correlation_id": request.correlation_id,
        "notes": request.notes,
        "submitted_at": request.submitted_at,
    }


def module_set_simulation_request_from_dict(data: dict) -> WorkbenchModuleSetSimulationRequest:
    """Parse a plain dict into a ``WorkbenchModuleSetSimulationRequest``. Raises
    ``KeyError``/``TypeError`` on a malformed request -- the canonical entrypoint catches these
    and reports ``WorkbenchRunErrorCode.MALFORMED_REQUEST``, never a traceback."""
    return WorkbenchModuleSetSimulationRequest(
        contract_version=data["contract_version"],
        run_id=data["run_id"],
        project_id=data["project_id"],
        subproject_id=data["subproject_id"],
        attach_payload=dict(data["attach_payload"]),
        module_id=data["module_id"],
        module_ports=tuple(data.get("module_ports") or ()),
        agent1_organism_id=data.get("agent1_organism_id"),
        input_artifact_references=dict(data.get("input_artifact_references") or {}),
        correlation_id=data.get("correlation_id"),
        notes=data.get("notes"),
        submitted_at=data.get("submitted_at"),
    )


def module_set_simulation_result_to_dict(result: WorkbenchModuleSetSimulationResult) -> dict:
    """Serialize a ``WorkbenchModuleSetSimulationResult`` to a plain, JSON-ready dict."""
    return {
        "contract_version": result.contract_version,
        "run_id": result.run_id,
        "status": result.status.value,
        "module_id": result.module_id,
        "module_handoff_summary": result.module_handoff_summary,
        "lineage": result.lineage,
        "agent3_report": result.agent3_report,
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


def module_set_simulation_result_from_dict(data: dict) -> WorkbenchModuleSetSimulationResult:
    """The inverse of ``module_set_simulation_result_to_dict`` -- used to load a cached result
    for replay."""
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
    return WorkbenchModuleSetSimulationResult(
        contract_version=data["contract_version"],
        run_id=data["run_id"],
        status=WorkbenchRunStatus(data["status"]),
        module_id=data.get("module_id"),
        module_handoff_summary=data.get("module_handoff_summary"),
        lineage=data.get("lineage"),
        agent3_report=data.get("agent3_report"),
        started_at=data.get("started_at"),
        completed_at=data.get("completed_at"),
        error=error,
        summary=data.get("summary", ""),
        warnings=tuple(data.get("warnings", ())),
        replayed=bool(data.get("replayed", False)),
    )


#: Model-Species Catalog Prerequisite increment -- a genuinely separate contract: this one
#: verifies a whole model's own already-generated Antimony text actually compiles, and reports
#: its real, loaded species/compartment identifiers. Agent 2 is never invoked here -- the
#: Workbench already has the Antimony text from its own prior full-model build.
WORKBENCH_MODEL_ANTIMONY_VERIFICATION_CONTRACT_VERSION = "workbench-model-antimony-verification-v1"


@dataclass(frozen=True, slots=True)
class WorkbenchModelAntimonyVerificationRequest:
    """What the Workbench sends to ask the harness to verify one whole model's own real,
    already-generated Antimony text."""

    contract_version: str
    run_id: str
    antimony_text: str
    correlation_id: str | None = None
    submitted_at: str | None = None


@dataclass(frozen=True, slots=True)
class WorkbenchModelAntimonyVerificationResult:
    """What the harness reports back for one ``WorkbenchModelAntimonyVerificationRequest``.

    ``status`` is ``SUCCEEDED`` whenever the verification *ran* (even when ``load_succeeded``
    is ``False`` -- an Antimony compilation failure is a real, reported outcome, never an
    infrastructure error) -- only a genuine infrastructure defect (an Agent 3 subprocess crash/
    timeout/malformed output) ever reports ``FAILED`` here.
    """

    contract_version: str
    run_id: str
    status: WorkbenchRunStatus
    load_succeeded: bool
    load_message: str | None
    floating_species_ids: tuple[str, ...]
    boundary_species_ids: tuple[str, ...]
    compartment_ids: tuple[str, ...]
    antimony_version: str | None
    roadrunner_version: str | None
    started_at: str | None
    completed_at: str | None
    error: WorkbenchRunError | None
    summary: str
    replayed: bool = False
    #: Joint Calibration Workflow prerequisite increment (Workbench ``docs/31``): every real,
    #: compiled global parameter id -- appended fields, defaulted to ``()``, so every existing
    #: caller/fixture that constructs this dataclass without them (pre-dating this increment)
    #: keeps working unchanged.
    global_parameter_ids: tuple[str, ...] = ()
    #: The subset of ``global_parameter_ids`` that an SBML assignment rule actually computes --
    #: never independently settable/fittable. See ``app.harness.runners
    #: .run_agent3_inspect_antimony_model`` for exactly how this is determined and why
    #: ``getAssignmentRuleIds`` itself is unusable from Python.
    assignment_rule_derived_parameter_ids: tuple[str, ...] = ()


def model_antimony_verification_request_to_dict(
    request: WorkbenchModelAntimonyVerificationRequest,
) -> dict:
    """Serialize a ``WorkbenchModelAntimonyVerificationRequest`` to a plain, JSON-ready dict."""
    return {
        "contract_version": request.contract_version,
        "run_id": request.run_id,
        "antimony_text": request.antimony_text,
        "correlation_id": request.correlation_id,
        "submitted_at": request.submitted_at,
    }


def model_antimony_verification_request_from_dict(
    data: dict,
) -> WorkbenchModelAntimonyVerificationRequest:
    """Parse a plain dict into a ``WorkbenchModelAntimonyVerificationRequest``. Raises
    ``KeyError``/``TypeError`` on a malformed request -- the canonical entrypoint catches these
    and reports ``WorkbenchRunErrorCode.MALFORMED_REQUEST``, never a traceback."""
    return WorkbenchModelAntimonyVerificationRequest(
        contract_version=data["contract_version"],
        run_id=data["run_id"],
        antimony_text=data["antimony_text"],
        correlation_id=data.get("correlation_id"),
        submitted_at=data.get("submitted_at"),
    )


def model_antimony_verification_result_to_dict(
    result: WorkbenchModelAntimonyVerificationResult,
) -> dict:
    """Serialize a ``WorkbenchModelAntimonyVerificationResult`` to a plain, JSON-ready dict."""
    return {
        "contract_version": result.contract_version,
        "run_id": result.run_id,
        "status": result.status.value,
        "load_succeeded": result.load_succeeded,
        "load_message": result.load_message,
        "floating_species_ids": list(result.floating_species_ids),
        "boundary_species_ids": list(result.boundary_species_ids),
        "compartment_ids": list(result.compartment_ids),
        "antimony_version": result.antimony_version,
        "roadrunner_version": result.roadrunner_version,
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
        "replayed": result.replayed,
        "global_parameter_ids": list(result.global_parameter_ids),
        "assignment_rule_derived_parameter_ids": list(
            result.assignment_rule_derived_parameter_ids
        ),
    }


def model_antimony_verification_result_from_dict(
    data: dict,
) -> WorkbenchModelAntimonyVerificationResult:
    """The inverse of ``model_antimony_verification_result_to_dict`` -- used to load a cached
    result for replay."""
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
    return WorkbenchModelAntimonyVerificationResult(
        contract_version=data["contract_version"],
        run_id=data["run_id"],
        status=WorkbenchRunStatus(data["status"]),
        load_succeeded=bool(data["load_succeeded"]),
        load_message=data.get("load_message"),
        floating_species_ids=tuple(data.get("floating_species_ids", ())),
        boundary_species_ids=tuple(data.get("boundary_species_ids", ())),
        compartment_ids=tuple(data.get("compartment_ids", ())),
        antimony_version=data.get("antimony_version"),
        roadrunner_version=data.get("roadrunner_version"),
        started_at=data.get("started_at"),
        completed_at=data.get("completed_at"),
        error=error,
        summary=data.get("summary", ""),
        replayed=bool(data.get("replayed", False)),
        global_parameter_ids=tuple(data.get("global_parameter_ids", ())),
        assignment_rule_derived_parameter_ids=tuple(
            data.get("assignment_rule_derived_parameter_ids", ())
        ),
    )


#: Whole-Model Experimental-Scenario Evaluation increment -- a genuinely separate contract: this
#: one evaluates one experimental scenario (explicit candidate parameter values, explicit
#: initial-condition/step-intervention overrides, explicit requested output times) against one
#: whole model's own real, already-generated Antimony text, through Agent 3's own
#: ``app.agent3.scenario_evaluation`` directly -- never Agent 2 (no new build is needed; the
#: Workbench already has the Antimony text), never Agent 4 (this is prediction, not fitting).
WORKBENCH_MODEL_SCENARIO_EVALUATION_CONTRACT_VERSION = "workbench-model-scenario-evaluation-v1"


@dataclass(frozen=True, slots=True)
class WorkbenchStepIntervention:
    """One step change applied *during* a trajectory, at its own declared ``time`` -- mirrors
    ``app.agent3.scenario_evaluation.StepIntervention`` exactly (``target_kind`` is
    ``"SPECIES"``/``"PARAMETER"``)."""

    target_kind: str
    target_id: str
    time: float
    value: float


@dataclass(frozen=True, slots=True)
class WorkbenchModelScenarioEvaluationRequest:
    """What the Workbench sends to ask the harness to evaluate one experimental scenario
    against one whole model's own real, already-generated Antimony text.

    Every identifier field (``parameter_overrides``/``initial_value_overrides`` keys, every
    ``interventions[*].target_id``, every ``requested_output_ids`` entry) is validated against
    the real, compiled model by Agent 3 itself (``app.agent3.scenario_evaluation
    ._validate_request``) -- never trusted from the Workbench's own catalog without that
    independent check. Conflicting-assignment/dosing-schedule rejection is the Workbench's own
    responsibility, before this request is ever built; this contract represents one, single,
    already-resolved scenario.
    """

    contract_version: str
    run_id: str
    antimony_text: str
    requested_times: tuple[float, ...]
    requested_output_ids: tuple[str, ...]
    parameter_overrides: dict[str, float] = field(default_factory=dict)
    initial_value_overrides: dict[str, float] = field(default_factory=dict)
    interventions: tuple[WorkbenchStepIntervention, ...] = ()
    integrator: str = "cvode"
    absolute_tolerance: float = 1e-10
    relative_tolerance: float = 1e-8
    correlation_id: str | None = None
    submitted_at: str | None = None


@dataclass(frozen=True, slots=True)
class WorkbenchModelScenarioEvaluationResult:
    """What the harness reports back for one ``WorkbenchModelScenarioEvaluationRequest``.

    ``status`` is ``SUCCEEDED`` whenever the evaluation *ran* -- even when
    ``evaluation_status`` is not ``"SUCCESS"`` (a real, reported scientific/request-validation
    outcome, e.g. an unresolved identifier or a divergent trajectory, never an infrastructure
    error). Only a genuine infrastructure defect (an Agent 3 subprocess crash/timeout/malformed
    output) ever reports ``FAILED`` here. ``evaluation_status`` is one of
    ``app.agent3.scenario_evaluation.ScenarioEvaluationStatus``'s own values, carried through
    verbatim as a plain string (this repository never imports Agent 3's own package).
    """

    contract_version: str
    run_id: str
    status: WorkbenchRunStatus
    evaluation_status: str
    predictions: dict[str, tuple[float, ...]] | None
    validation_errors: tuple[str, ...]
    solver_message: str | None
    antimony_version: str | None
    roadrunner_version: str | None
    started_at: str | None
    completed_at: str | None
    error: WorkbenchRunError | None
    summary: str
    replayed: bool = False


def _step_intervention_to_dict(iv: WorkbenchStepIntervention) -> dict:
    return {
        "target_kind": iv.target_kind,
        "target_id": iv.target_id,
        "time": iv.time,
        "value": iv.value,
    }


def _step_intervention_from_dict(data: dict) -> WorkbenchStepIntervention:
    return WorkbenchStepIntervention(
        target_kind=data["target_kind"],
        target_id=data["target_id"],
        time=data["time"],
        value=data["value"],
    )


def model_scenario_evaluation_request_to_dict(
    request: WorkbenchModelScenarioEvaluationRequest,
) -> dict:
    """Serialize a ``WorkbenchModelScenarioEvaluationRequest`` to a plain, JSON-ready dict."""
    return {
        "contract_version": request.contract_version,
        "run_id": request.run_id,
        "antimony_text": request.antimony_text,
        "requested_times": list(request.requested_times),
        "requested_output_ids": list(request.requested_output_ids),
        "parameter_overrides": dict(request.parameter_overrides),
        "initial_value_overrides": dict(request.initial_value_overrides),
        "interventions": [_step_intervention_to_dict(iv) for iv in request.interventions],
        "integrator": request.integrator,
        "absolute_tolerance": request.absolute_tolerance,
        "relative_tolerance": request.relative_tolerance,
        "correlation_id": request.correlation_id,
        "submitted_at": request.submitted_at,
    }


def model_scenario_evaluation_request_from_dict(
    data: dict,
) -> WorkbenchModelScenarioEvaluationRequest:
    """Parse a plain dict into a ``WorkbenchModelScenarioEvaluationRequest``. Raises
    ``KeyError``/``TypeError`` on a malformed request -- the canonical entrypoint catches these
    and reports ``WorkbenchRunErrorCode.MALFORMED_REQUEST``, never a traceback."""
    return WorkbenchModelScenarioEvaluationRequest(
        contract_version=data["contract_version"],
        run_id=data["run_id"],
        antimony_text=data["antimony_text"],
        requested_times=tuple(data["requested_times"]),
        requested_output_ids=tuple(data["requested_output_ids"]),
        parameter_overrides=dict(data.get("parameter_overrides", {})),
        initial_value_overrides=dict(data.get("initial_value_overrides", {})),
        interventions=tuple(
            _step_intervention_from_dict(iv) for iv in data.get("interventions", ())
        ),
        integrator=data.get("integrator", "cvode"),
        absolute_tolerance=data.get("absolute_tolerance", 1e-10),
        relative_tolerance=data.get("relative_tolerance", 1e-8),
        correlation_id=data.get("correlation_id"),
        submitted_at=data.get("submitted_at"),
    )


def model_scenario_evaluation_result_to_dict(
    result: WorkbenchModelScenarioEvaluationResult,
) -> dict:
    """Serialize a ``WorkbenchModelScenarioEvaluationResult`` to a plain, JSON-ready dict."""
    return {
        "contract_version": result.contract_version,
        "run_id": result.run_id,
        "status": result.status.value,
        "evaluation_status": result.evaluation_status,
        "predictions": (
            None
            if result.predictions is None
            else {k: list(v) for k, v in result.predictions.items()}
        ),
        "validation_errors": list(result.validation_errors),
        "solver_message": result.solver_message,
        "antimony_version": result.antimony_version,
        "roadrunner_version": result.roadrunner_version,
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
        "replayed": result.replayed,
    }


def model_scenario_evaluation_result_from_dict(
    data: dict,
) -> WorkbenchModelScenarioEvaluationResult:
    """The inverse of ``model_scenario_evaluation_result_to_dict`` -- used to load a cached
    result for replay."""
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
    predictions_data = data.get("predictions")
    predictions = (
        None
        if predictions_data is None
        else {k: tuple(v) for k, v in predictions_data.items()}
    )
    return WorkbenchModelScenarioEvaluationResult(
        contract_version=data["contract_version"],
        run_id=data["run_id"],
        status=WorkbenchRunStatus(data["status"]),
        evaluation_status=data["evaluation_status"],
        predictions=predictions,
        validation_errors=tuple(data.get("validation_errors", ())),
        solver_message=data.get("solver_message"),
        antimony_version=data.get("antimony_version"),
        roadrunner_version=data.get("roadrunner_version"),
        started_at=data.get("started_at"),
        completed_at=data.get("completed_at"),
        error=error,
        summary=data.get("summary", ""),
        replayed=bool(data.get("replayed", False)),
    )


#: Whole-Model Antimony Import increment -- a genuinely separate contract: this one audits
#: fidelity (rule/event counts, which construct -- if any -- was rejected and why) for
#: caller-supplied Antimony text through Agent 2's own, pre-existing, unmodified
#: ``app.agent2.antimony_import.import_antimony`` directly -- never Agent 1, never a
#: structured network. Deliberately independent of ``model_antimony_verification`` (which
#: still does the real executability check and species/parameter/compartment catalog capture,
#: through Agent 3, unmodified) -- this contract is audit-only and never a replacement for it.
WORKBENCH_MODEL_ANTIMONY_IMPORT_CONTRACT_VERSION = "workbench-model-antimony-import-v1"


@dataclass(frozen=True, slots=True)
class WorkbenchModelAntimonyImportRequest:
    """What the Workbench sends to audit one whole model's own caller-supplied (never Agent
    1/2-produced) Antimony text for import fidelity."""

    contract_version: str
    run_id: str
    antimony_text: str
    correlation_id: str | None = None
    submitted_at: str | None = None


@dataclass(frozen=True, slots=True)
class WorkbenchModelAntimonyImportResult:
    """What the harness reports back for one ``WorkbenchModelAntimonyImportRequest``.

    ``status`` is ``SUCCEEDED`` whenever the import attempt *ran* -- even when
    ``import_succeeded`` is ``False`` (a real, reported, disclosed outcome: malformed source,
    an unsupported construct, or an ambiguous module -- never an infrastructure error).
    ``import_error_kind`` is one of ``"MALFORMED"``/``"UNSUPPORTED_CONSTRUCT"``/
    ``"AMBIGUOUS_MODULE"`` (mirroring Agent 2's own three-exception hierarchy verbatim,
    ``app.agent2.antimony_import.errors``), or ``None`` when ``import_succeeded`` is ``True``.
    """

    contract_version: str
    run_id: str
    status: WorkbenchRunStatus
    import_succeeded: bool
    import_error_kind: str | None
    import_message: str | None
    compartment_ids: tuple[str, ...]
    #: ``compartment_id`` -> Agent 2's own structural display name (``is "..."`` directives;
    #: otherwise identical to the id) -- a detail Agent-3-side verification has no notion of.
    compartment_names: dict[str, str]
    species_ids: tuple[str, ...]
    #: ``species_id`` -> its own compartment id -- Agent 2's own structural context,
    #: unavailable from Agent-3-side verification's flat species-id lists alone.
    species_compartment_ids: dict[str, str]
    parameter_ids: tuple[str, ...]
    reaction_ids: tuple[str, ...]
    assignment_rule_count: int
    rate_rule_count: int
    algebraic_rule_count: int
    event_count: int
    antimony_import_parser_version: str | None
    started_at: str | None
    completed_at: str | None
    error: WorkbenchRunError | None
    summary: str
    replayed: bool = False


def model_antimony_import_request_to_dict(request: WorkbenchModelAntimonyImportRequest) -> dict:
    """Serialize a ``WorkbenchModelAntimonyImportRequest`` to a plain, JSON-ready dict."""
    return {
        "contract_version": request.contract_version,
        "run_id": request.run_id,
        "antimony_text": request.antimony_text,
        "correlation_id": request.correlation_id,
        "submitted_at": request.submitted_at,
    }


def model_antimony_import_request_from_dict(data: dict) -> WorkbenchModelAntimonyImportRequest:
    """Parse a plain dict into a ``WorkbenchModelAntimonyImportRequest``. Raises
    ``KeyError``/``TypeError`` on a malformed request -- the canonical entrypoint catches these
    and reports ``WorkbenchRunErrorCode.MALFORMED_REQUEST``, never a traceback."""
    return WorkbenchModelAntimonyImportRequest(
        contract_version=data["contract_version"],
        run_id=data["run_id"],
        antimony_text=data["antimony_text"],
        correlation_id=data.get("correlation_id"),
        submitted_at=data.get("submitted_at"),
    )


def model_antimony_import_result_to_dict(result: WorkbenchModelAntimonyImportResult) -> dict:
    """Serialize a ``WorkbenchModelAntimonyImportResult`` to a plain, JSON-ready dict."""
    return {
        "contract_version": result.contract_version,
        "run_id": result.run_id,
        "status": result.status.value,
        "import_succeeded": result.import_succeeded,
        "import_error_kind": result.import_error_kind,
        "import_message": result.import_message,
        "compartment_ids": list(result.compartment_ids),
        "compartment_names": dict(result.compartment_names),
        "species_ids": list(result.species_ids),
        "species_compartment_ids": dict(result.species_compartment_ids),
        "parameter_ids": list(result.parameter_ids),
        "reaction_ids": list(result.reaction_ids),
        "assignment_rule_count": result.assignment_rule_count,
        "rate_rule_count": result.rate_rule_count,
        "algebraic_rule_count": result.algebraic_rule_count,
        "event_count": result.event_count,
        "antimony_import_parser_version": result.antimony_import_parser_version,
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
        "replayed": result.replayed,
    }


def model_antimony_import_result_from_dict(data: dict) -> WorkbenchModelAntimonyImportResult:
    """The inverse of ``model_antimony_import_result_to_dict`` -- used to load a cached result
    for replay."""
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
    return WorkbenchModelAntimonyImportResult(
        contract_version=data["contract_version"],
        run_id=data["run_id"],
        status=WorkbenchRunStatus(data["status"]),
        import_succeeded=bool(data["import_succeeded"]),
        import_error_kind=data.get("import_error_kind"),
        import_message=data.get("import_message"),
        compartment_ids=tuple(data.get("compartment_ids", ())),
        compartment_names=dict(data.get("compartment_names", {})),
        species_ids=tuple(data.get("species_ids", ())),
        species_compartment_ids=dict(data.get("species_compartment_ids", {})),
        parameter_ids=tuple(data.get("parameter_ids", ())),
        reaction_ids=tuple(data.get("reaction_ids", ())),
        assignment_rule_count=data.get("assignment_rule_count", 0),
        rate_rule_count=data.get("rate_rule_count", 0),
        algebraic_rule_count=data.get("algebraic_rule_count", 0),
        event_count=data.get("event_count", 0),
        antimony_import_parser_version=data.get("antimony_import_parser_version"),
        started_at=data.get("started_at"),
        completed_at=data.get("completed_at"),
        error=error,
        summary=data.get("summary", ""),
        replayed=bool(data.get("replayed", False)),
    )


#: Module-Level Agent4 Calibration increment -- a fifth, genuinely separate contract: this one
#: names calibrating one already-accepted hierarchy module's own standalone executable
#: artifact through Agent 2, Agent 3, then Agent 4 against Workbench-supplied experimental
#: data -- never the whole root model, never Agent 2/3/4 code changed. Deliberately its own
#: version.
WORKBENCH_MODULE_CALIBRATION_CONTRACT_VERSION = "workbench-module-calibration-v1"


@dataclass(frozen=True, slots=True)
class WorkbenchModuleCalibrationRequest:
    """What the Workbench sends to ask the harness to calibrate one accepted hierarchy module.

    ``attach_payload`` is the Workbench's own stored, verbatim-opaque copy of a prior
    ``WorkbenchHierarchyNodeSummary.attach_payload``, with the module's own resolved boundary
    ports already merged in as ``module_ports`` -- passed back here unchanged, mirroring
    ``WorkbenchModuleSimulationRequest``'s own identical field exactly. ``calibration_request``
    is Agent 4's own ``CalibrationRequest`` dict shape (``targets``/``observations``/
    ``optimizer``/...), built and validated entirely by the Workbench -- never reshaped here.
    """

    contract_version: str
    run_id: str
    project_id: str
    subproject_id: str
    attach_payload: dict
    module_id: str
    calibration_request: dict
    agent1_organism_id: str | None = None
    input_artifact_references: dict[str, str] = field(default_factory=dict)
    correlation_id: str | None = None
    notes: str | None = None
    submitted_at: str | None = None


@dataclass(frozen=True, slots=True)
class WorkbenchModuleCalibrationResult:
    """What the harness reports back for one ``WorkbenchModuleCalibrationRequest``."""

    contract_version: str
    run_id: str
    status: WorkbenchRunStatus
    module_id: str | None
    modularization_id: str | None
    #: The full, materialized Agent2->Agent3 handoff dict (species/reactions/kinetic_laws/
    #: parameters/antimony_text), never a bare summary -- the Workbench's own immutable
    #: execution-snapshot persistence needs real parameter/initial-condition fidelity, not
    #: just counts.
    module_handoff: dict | None
    #: Agent 3's own full ``Agent3Report`` dict, read verbatim.
    agent3_report: dict | None
    #: Agent 4's own full ``Agent4Report`` dict, read verbatim -- including every
    #: ``parameter_estimates``/``residuals``/``identifiability_findings`` entry, never
    #: compressed down the way ``app.harness.module_calibration``'s own
    #: ``ModuleCalibrationEvaluation`` mapping does for its own, different consumer.
    agent4_report: dict | None
    started_at: str | None
    completed_at: str | None
    error: WorkbenchRunError | None
    summary: str
    warnings: tuple[str, ...] = ()
    replayed: bool = False


def module_calibration_request_to_dict(request: WorkbenchModuleCalibrationRequest) -> dict:
    """Serialize a ``WorkbenchModuleCalibrationRequest`` to a plain, JSON-ready dict."""
    return {
        "contract_version": request.contract_version,
        "run_id": request.run_id,
        "project_id": request.project_id,
        "subproject_id": request.subproject_id,
        "attach_payload": dict(request.attach_payload),
        "module_id": request.module_id,
        "calibration_request": dict(request.calibration_request),
        "agent1_organism_id": request.agent1_organism_id,
        "input_artifact_references": dict(request.input_artifact_references),
        "correlation_id": request.correlation_id,
        "notes": request.notes,
        "submitted_at": request.submitted_at,
    }


def module_calibration_request_from_dict(data: dict) -> WorkbenchModuleCalibrationRequest:
    """Parse a plain dict into a ``WorkbenchModuleCalibrationRequest``. Raises
    ``KeyError``/``TypeError`` on a malformed request -- the canonical entrypoint catches these
    and reports ``WorkbenchRunErrorCode.MALFORMED_REQUEST``, never a traceback."""
    return WorkbenchModuleCalibrationRequest(
        contract_version=data["contract_version"],
        run_id=data["run_id"],
        project_id=data["project_id"],
        subproject_id=data["subproject_id"],
        attach_payload=dict(data["attach_payload"]),
        module_id=data["module_id"],
        calibration_request=dict(data["calibration_request"]),
        agent1_organism_id=data.get("agent1_organism_id"),
        input_artifact_references=dict(data.get("input_artifact_references") or {}),
        correlation_id=data.get("correlation_id"),
        notes=data.get("notes"),
        submitted_at=data.get("submitted_at"),
    )


def module_calibration_result_to_dict(result: WorkbenchModuleCalibrationResult) -> dict:
    """Serialize a ``WorkbenchModuleCalibrationResult`` to a plain, JSON-ready dict."""
    return {
        "contract_version": result.contract_version,
        "run_id": result.run_id,
        "status": result.status.value,
        "module_id": result.module_id,
        "modularization_id": result.modularization_id,
        "module_handoff": result.module_handoff,
        "agent3_report": result.agent3_report,
        "agent4_report": result.agent4_report,
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


def module_calibration_result_from_dict(data: dict) -> WorkbenchModuleCalibrationResult:
    """The inverse of ``module_calibration_result_to_dict`` -- used to load a cached result for
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
    return WorkbenchModuleCalibrationResult(
        contract_version=data["contract_version"],
        run_id=data["run_id"],
        status=WorkbenchRunStatus(data["status"]),
        module_id=data.get("module_id"),
        modularization_id=data.get("modularization_id"),
        module_handoff=data.get("module_handoff"),
        agent3_report=data.get("agent3_report"),
        agent4_report=data.get("agent4_report"),
        started_at=data.get("started_at"),
        completed_at=data.get("completed_at"),
        error=error,
        summary=data.get("summary", ""),
        warnings=tuple(data.get("warnings", ())),
        replayed=bool(data.get("replayed", False)),
    )


#: Module-Level Agent5 Validation and Experimental Design increment -- a sixth, genuinely
#: separate contract: this one names validating one already-calibrated hierarchy module's own
#: frozen parameter estimates against independent held-out experimental data through Agent 2
#: then Agent 5 -- never Agent 3/Agent 4, never the whole root model. Deliberately its own
#: version.
WORKBENCH_MODULE_VALIDATION_CONTRACT_VERSION = "workbench-module-validation-v1"


@dataclass(frozen=True, slots=True)
class WorkbenchModuleValidationRequest:
    """What the Workbench sends to ask the harness to validate one already-calibrated
    hierarchy module.

    ``attach_payload`` is the Workbench's own stored, verbatim-opaque copy of a prior
    ``HierarchyNodeSummary.attach_payload``, with the module's own resolved boundary ports
    already merged in as ``module_ports`` -- passed back here unchanged, mirroring
    ``WorkbenchModuleCalibrationRequest``'s own identical field exactly. ``agent4_report`` is
    the full, verbatim report dict a *prior, already-succeeded* module-calibration execution
    produced -- Agent 3/Agent 4 are never re-invoked by this contract. ``validation_request``
    is Agent 5's own ``ValidationRequest`` dict shape (``request_id``/
    ``validation_observations``/``candidate_experiments``/...), built and validated by the
    Workbench before this request is ever sent.
    """

    contract_version: str
    run_id: str
    project_id: str
    subproject_id: str
    attach_payload: dict
    module_id: str
    agent4_report: dict
    validation_request: dict
    agent1_organism_id: str | None = None
    input_artifact_references: dict[str, str] = field(default_factory=dict)
    correlation_id: str | None = None
    notes: str | None = None
    submitted_at: str | None = None


@dataclass(frozen=True, slots=True)
class WorkbenchModuleValidationResult:
    """What the harness reports back for one ``WorkbenchModuleValidationRequest``."""

    contract_version: str
    run_id: str
    status: WorkbenchRunStatus
    module_id: str | None
    modularization_id: str | None
    #: The full, materialized Agent2->Agent3 handoff dict -- never a bare summary.
    module_handoff: dict | None
    #: Agent 5's own full ``Agent5Report`` dict, read verbatim -- every ``validation``/
    #: ``generalization_findings``/``candidate_experiments``/``experiment_scores``/
    #: ``experimental_design_findings`` entry, never compressed.
    agent5_report: dict | None
    started_at: str | None
    completed_at: str | None
    error: WorkbenchRunError | None
    summary: str
    warnings: tuple[str, ...] = ()
    replayed: bool = False


def module_validation_request_to_dict(request: WorkbenchModuleValidationRequest) -> dict:
    """Serialize a ``WorkbenchModuleValidationRequest`` to a plain, JSON-ready dict."""
    return {
        "contract_version": request.contract_version,
        "run_id": request.run_id,
        "project_id": request.project_id,
        "subproject_id": request.subproject_id,
        "attach_payload": dict(request.attach_payload),
        "module_id": request.module_id,
        "agent4_report": dict(request.agent4_report),
        "validation_request": dict(request.validation_request),
        "agent1_organism_id": request.agent1_organism_id,
        "input_artifact_references": dict(request.input_artifact_references),
        "correlation_id": request.correlation_id,
        "notes": request.notes,
        "submitted_at": request.submitted_at,
    }


def module_validation_request_from_dict(data: dict) -> WorkbenchModuleValidationRequest:
    """Parse a plain dict into a ``WorkbenchModuleValidationRequest``. Raises
    ``KeyError``/``TypeError`` on a malformed request -- the canonical entrypoint catches these
    and reports ``WorkbenchRunErrorCode.MALFORMED_REQUEST``, never a traceback."""
    return WorkbenchModuleValidationRequest(
        contract_version=data["contract_version"],
        run_id=data["run_id"],
        project_id=data["project_id"],
        subproject_id=data["subproject_id"],
        attach_payload=dict(data["attach_payload"]),
        module_id=data["module_id"],
        agent4_report=dict(data["agent4_report"]),
        validation_request=dict(data["validation_request"]),
        agent1_organism_id=data.get("agent1_organism_id"),
        input_artifact_references=dict(data.get("input_artifact_references") or {}),
        correlation_id=data.get("correlation_id"),
        notes=data.get("notes"),
        submitted_at=data.get("submitted_at"),
    )


def module_validation_result_to_dict(result: WorkbenchModuleValidationResult) -> dict:
    """Serialize a ``WorkbenchModuleValidationResult`` to a plain, JSON-ready dict."""
    return {
        "contract_version": result.contract_version,
        "run_id": result.run_id,
        "status": result.status.value,
        "module_id": result.module_id,
        "modularization_id": result.modularization_id,
        "module_handoff": result.module_handoff,
        "agent5_report": result.agent5_report,
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


def module_validation_result_from_dict(data: dict) -> WorkbenchModuleValidationResult:
    """The inverse of ``module_validation_result_to_dict`` -- used to load a cached result for
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
    return WorkbenchModuleValidationResult(
        contract_version=data["contract_version"],
        run_id=data["run_id"],
        status=WorkbenchRunStatus(data["status"]),
        module_id=data.get("module_id"),
        modularization_id=data.get("modularization_id"),
        module_handoff=data.get("module_handoff"),
        agent5_report=data.get("agent5_report"),
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
    "WORKBENCH_HIERARCHICAL_CONTRACT_VERSION",
    "WORKBENCH_HIERARCHICAL_RESUME_CONTRACT_VERSION",
    "WORKBENCH_MODEL_ANTIMONY_IMPORT_CONTRACT_VERSION",
    "WORKBENCH_MODEL_ANTIMONY_VERIFICATION_CONTRACT_VERSION",
    "WORKBENCH_MODEL_SCENARIO_EVALUATION_CONTRACT_VERSION",
    "WORKBENCH_MODULE_BOUNDARY_DERIVATION_CONTRACT_VERSION",
    "WORKBENCH_MODULE_CALIBRATION_CONTRACT_VERSION",
    "WORKBENCH_MODULE_REMATERIALIZATION_CONTRACT_VERSION",
    "WORKBENCH_MODULE_SET_SIMULATION_CONTRACT_VERSION",
    "WORKBENCH_MODULE_SIMULATION_CONTRACT_VERSION",
    "WORKBENCH_MODULE_VALIDATION_CONTRACT_VERSION",
    "WorkbenchHierarchicalInvocationRequest",
    "WorkbenchHierarchicalResumeRequest",
    "WorkbenchHierarchicalRunResult",
    "WorkbenchHierarchyNodeSummary",
    "WorkbenchInvocationRequest",
    "WorkbenchModelAntimonyImportRequest",
    "WorkbenchModelAntimonyImportResult",
    "WorkbenchModelAntimonyVerificationRequest",
    "WorkbenchModelAntimonyVerificationResult",
    "WorkbenchModelScenarioEvaluationRequest",
    "WorkbenchModelScenarioEvaluationResult",
    "WorkbenchModuleBoundaryDerivationRequest",
    "WorkbenchModuleBoundaryDerivationResult",
    "WorkbenchModuleCalibrationRequest",
    "WorkbenchModuleCalibrationResult",
    "WorkbenchModuleRematerializationRequest",
    "WorkbenchModuleRematerializationResult",
    "WorkbenchModuleSetSimulationRequest",
    "WorkbenchModuleSetSimulationResult",
    "WorkbenchModuleSimulationRequest",
    "WorkbenchModuleSimulationResult",
    "WorkbenchModuleValidationRequest",
    "WorkbenchModuleValidationResult",
    "WorkbenchRunError",
    "WorkbenchRunErrorCode",
    "WorkbenchRunResult",
    "WorkbenchRunStatus",
    "WorkbenchStepIntervention",
    "hierarchical_request_from_dict",
    "hierarchical_result_from_dict",
    "hierarchical_result_to_dict",
    "hierarchical_resume_request_from_dict",
    "hierarchical_resume_request_to_dict",
    "model_antimony_import_request_from_dict",
    "model_antimony_import_request_to_dict",
    "model_antimony_import_result_from_dict",
    "model_antimony_import_result_to_dict",
    "model_antimony_verification_request_from_dict",
    "model_antimony_verification_request_to_dict",
    "model_antimony_verification_result_from_dict",
    "model_antimony_verification_result_to_dict",
    "model_scenario_evaluation_request_from_dict",
    "model_scenario_evaluation_request_to_dict",
    "model_scenario_evaluation_result_from_dict",
    "model_scenario_evaluation_result_to_dict",
    "module_boundary_derivation_request_from_dict",
    "module_boundary_derivation_request_to_dict",
    "module_boundary_derivation_result_from_dict",
    "module_boundary_derivation_result_to_dict",
    "module_calibration_request_from_dict",
    "module_calibration_request_to_dict",
    "module_calibration_result_from_dict",
    "module_calibration_result_to_dict",
    "module_rematerialization_request_from_dict",
    "module_rematerialization_request_to_dict",
    "module_rematerialization_result_from_dict",
    "module_rematerialization_result_to_dict",
    "module_set_simulation_request_from_dict",
    "module_set_simulation_request_to_dict",
    "module_set_simulation_result_from_dict",
    "module_set_simulation_result_to_dict",
    "module_simulation_request_from_dict",
    "module_simulation_request_to_dict",
    "module_simulation_result_from_dict",
    "module_simulation_result_to_dict",
    "module_validation_request_from_dict",
    "module_validation_request_to_dict",
    "module_validation_result_from_dict",
    "module_validation_result_to_dict",
    "request_from_dict",
    "result_from_dict",
    "result_to_dict",
]
