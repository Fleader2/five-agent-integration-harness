#!/usr/bin/env python3
"""Canonical entrypoint for a Workbench-invoked hierarchical recursive modularization search.

Usage::

    .venv/bin/python3 scripts/run_workbench_hierarchical_request.py \\
        --request /path/to/workbench_hierarchical_invocation_request.json \\
        --output /path/to/workbench_hierarchical_run_result.json

See ``docs/15_workbench_hierarchical_recursion_contract.md`` for the full contract
documentation; this script adds a request/result contract around the exact, pre-existing
``app.harness.hierarchical_recursion.run_hierarchical_recursive_modularization`` mechanism --
nothing about hierarchical recursion itself is duplicated or reimplemented here, mirroring
``run_workbench_request.py``'s own identical relationship to ``run_workflow``.

**Execution semantics, in order (mirrors ``run_workbench_request.py``'s own numbered list):**

1. Parse ``--request`` as a ``WorkbenchHierarchicalInvocationRequest``
   (``app.harness.workbench_contracts``). A malformed request is reported as
   ``MALFORMED_REQUEST``, never an uncaught exception.
2. **Idempotent replay.** If
   ``artifacts/runs/<run_id>/workbench_hierarchical_result.json`` already exists, it is read
   and returned unchanged, with ``replayed=True`` set on the *returned* copy -- no search is
   re-run, and the original cached artifact is never rewritten.
3. ``contract_version`` is checked against ``WORKBENCH_HIERARCHICAL_CONTRACT_VERSION`` -- a
   mismatch is ``CONTRACT_VERSION_MISMATCH`` and nothing runs.
4. Exactly one of ``agent1_organism_id`` or
   ``input_artifact_references["stage1_synthetic_source"]`` must be set -- otherwise
   ``INVALID_STAGE1_INPUT``. When ``agent1_organism_id`` is given, Agent 1 is invoked as a real
   subprocess (``run_agent1.py``) exactly as ``app.harness.pipeline.run_workflow``'s own Stage 1
   already does; the synthetic-source path is test/dev-only infrastructure, documented as such
   (identical convention to the FULL_PIPELINE contract).
5. The real ``run_hierarchical_recursive_modularization`` runs, with a calibration dataset
   provider that always returns ``None`` (see the contract's own disclosed scope note) and the
   real ``invoke_agent2_candidate_search_round``/``run_module_calibration_workflow``/
   ``run_module_functional_evaluation_workflow`` callables (unchanged) -- no fakes, no
   injected test doubles, this is the production entrypoint.
6. The full, unabridged ``HierarchicalRecursionResult`` (every node, exactly as the orchestrator
   produced it) is written to ``hierarchical_recursion_result.json`` for full traceability, and
   reshaped into ``WorkbenchHierarchicalRunResult``, written to both
   ``artifacts/runs/<run_id>/workbench_hierarchical_result.json`` (the durable, replayable
   artifact) and ``--output`` (this invocation's own copy). When the run paused for human
   review, ``WorkbenchHierarchicalRunResult.checkpoint`` carries the harness's own
   ``serialize_checkpoint(...)`` dict verbatim -- see ``scripts/run_workbench_hierarchical_
   resume_request.py`` (human-review/resume increment), the sibling entrypoint that resumes
   from exactly this value.

No scientific logic lives here: this script never interprets, repairs, or re-derives any node's
own acceptance decision -- it only reshapes the already-existing ``HierarchicalRecursionResult``
into the Workbench's own contract shape.
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
from app.harness.hierarchical_recursion import (  # noqa: E402
    HierarchicalRecursionPolicy,
    run_hierarchical_recursive_modularization,
    serialize_checkpoint,
)
from app.harness.recursive_candidate_search import OrchestrationPolicy  # noqa: E402
from app.harness.subprocess_runner import run_stage_subprocess  # noqa: E402
from app.harness.workbench_contracts import (  # noqa: E402
    WORKBENCH_HIERARCHICAL_CONTRACT_VERSION,
    WorkbenchHierarchicalInvocationRequest,
    WorkbenchHierarchicalRunResult,
    WorkbenchHierarchyNodeSummary,
    WorkbenchRunError,
    WorkbenchRunErrorCode,
    WorkbenchRunStatus,
    hierarchical_request_from_dict,
    hierarchical_result_from_dict,
    hierarchical_result_to_dict,
)

_RUNNERS_DIR = _REPO_ROOT / "app" / "harness" / "runners"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _never_provide_dataset(**_kwargs) -> None:
    """The one, documented calibration-request-provider this entrypoint ever uses -- see the
    contract's own disclosed scope note: deciding what counts as a usable calibration dataset
    for an arbitrary candidate module is Agent 5's own future job, out of scope here. Every
    ``CALIBRATE`` decision therefore resolves as ``NO_DATASET_AVAILABLE``, never a fabricated
    dataset."""
    return None


def _rejection(
    *, run_id: str, code: WorkbenchRunErrorCode, message: str, warnings: tuple[str, ...] = ()
) -> WorkbenchHierarchicalRunResult:
    now = _now_iso()
    return WorkbenchHierarchicalRunResult(
        contract_version=WORKBENCH_HIERARCHICAL_CONTRACT_VERSION,
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


def _resolve_agent1_view_path(
    request: WorkbenchHierarchicalInvocationRequest, *, stage_dir: Path
) -> tuple[Path | None, WorkbenchHierarchicalRunResult | None, str | None]:
    """Returns ``(agent1_view_path, rejection_or_None, warning_or_None)``."""
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
    request: WorkbenchHierarchicalInvocationRequest, *, stage_dir: Path
) -> WorkbenchHierarchicalRunResult:
    warnings: list[str] = []
    agent1_view_path, rejection, warning = _resolve_agent1_view_path(request, stage_dir=stage_dir)
    if rejection is not None:
        return rejection
    if warning is not None:
        warnings.append(warning)
    assert agent1_view_path is not None

    recursion_data = request.recursion_policy
    recursion_policy = HierarchicalRecursionPolicy(
        max_depth=recursion_data["max_depth"],
        min_reactions_per_module=recursion_data["min_reactions_per_module"],
        max_total_hierarchy_nodes=recursion_data["max_total_hierarchy_nodes"],
        max_total_functional_evaluation_budget=recursion_data[
            "max_total_functional_evaluation_budget"
        ],
        max_total_calibration_budget=recursion_data["max_total_calibration_budget"],
        min_improvement_to_accept_child=recursion_data["min_improvement_to_accept_child"],
        require_human_review=recursion_data.get("require_human_review", False),
        policy_version=recursion_data["policy_version"],
    )
    flat_data = request.flat_orchestration_policy
    flat_orchestration_policy = OrchestrationPolicy(
        max_rounds=flat_data["max_rounds"],
        max_total_candidates=flat_data["max_total_candidates"],
        improvement_epsilon=flat_data["improvement_epsilon"],
        require_human_review=flat_data.get("require_human_review", False),
        policy_version=flat_data["policy_version"],
    )

    started_at = _now_iso()
    result = run_hierarchical_recursive_modularization(
        agent1_view_path=agent1_view_path,
        criteria_weights=request.criteria_weights,
        search_policy=request.search_policy,
        calibration_selection_policy=request.calibration_selection_policy,
        flat_orchestration_policy=flat_orchestration_policy,
        recursion_policy=recursion_policy,
        calibration_request_provider=_never_provide_dataset,
        stage_dir=stage_dir,
        correlation_id=request.correlation_id or request.run_id,
        run_id_prefix=request.run_id,
        functional_evaluation_selection_policy=request.functional_evaluation_selection_policy,
        exclude_single_module_from_ranking=request.exclude_single_module_from_ranking,
        apply_resolution_correction=request.apply_resolution_correction,
    )
    completed_at = _now_iso()
    warnings.append(
        "calibration_request_provider always returns no dataset for this entrypoint -- every "
        "CALIBRATE decision resolves as NO_DATASET_AVAILABLE. See the contract's own disclosed "
        "scope note."
    )

    _write(stage_dir / "hierarchical_recursion_result.json", dataclasses.asdict(result))

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
        f"{len(nodes)} node(s) explored; {sum(1 for n in nodes if n.accepted)} accepted; "
        f"root accepted={accepted_root is not None}; requires_user_review="
        f"{result.requires_user_review}"
    )

    return WorkbenchHierarchicalRunResult(
        contract_version=WORKBENCH_HIERARCHICAL_CONTRACT_VERSION,
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
        warnings=tuple(warnings) + tuple(result.warnings),
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
        request = hierarchical_request_from_dict(request_data)
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
    cached_result_path = stage_dir / "workbench_hierarchical_result.json"

    if cached_result_path.is_file():
        with open(cached_result_path) as f:
            cached = hierarchical_result_from_dict(json.load(f))
        replayed_result = dataclasses.replace(cached, replayed=True)
        _write(output_path, hierarchical_result_to_dict(replayed_result))
        print(f"status={replayed_result.status.value} (replayed run_id={request.run_id})")
        return 0 if replayed_result.status is WorkbenchRunStatus.SUCCEEDED else 1

    if request.contract_version != WORKBENCH_HIERARCHICAL_CONTRACT_VERSION:
        result = _rejection(
            run_id=request.run_id,
            code=WorkbenchRunErrorCode.CONTRACT_VERSION_MISMATCH,
            message=(
                f"Expected contract_version {WORKBENCH_HIERARCHICAL_CONTRACT_VERSION!r}, "
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
                message=(
                    f"Malformed policy field inside the request (missing/wrong-typed key): {exc!r}"
                ),
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
