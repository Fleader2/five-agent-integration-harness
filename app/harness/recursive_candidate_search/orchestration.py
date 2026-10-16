"""``run_recursive_candidate_search``: the harness's own recursive-loop driver -- the one place
in this project that both decides how many rounds to run / when to stop *and* routes real
calibration evidence through Agent 3 then Agent 4, closing the modularization loop (task
instructions §1).

**Agent 2 never calls Agent 3 or Agent 4.** This module is the one, explicit routing point:
each round's own candidate generation / structural scoring / calibration-selection gating /
request-building happens entirely inside Agent 2's own subprocess (``invoke_round``, by default
``agent2_round.invoke_agent2_candidate_search_round``); this module only ever decides, for each
``CALIBRATE`` decision Agent 2's own gate already produced, whether to reuse cached evidence,
request a dataset, or actually call ``app.harness.module_calibration.run_module_calibration_
workflow`` (unchanged) -- and then feeds whatever evidence results back into the next round's
own call to Agent 2.

**Never fabricates a dataset.** ``calibration_request_provider`` is always caller-supplied: this
module never invents calibration targets/observations for a module (that is Agent 5's future
job, out of scope here) -- a module with no provider-supplied dataset is recorded as
``NO_DATASET_AVAILABLE`` and simply never calibrated this round.
"""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.harness.module_calibration import (
    ModuleCalibrationWorkflowError,
    run_module_calibration_workflow,
)
from app.harness.module_functional_evaluation import (
    ModuleFunctionalEvaluationWorkflowError,
    run_module_functional_evaluation_workflow,
)
from app.harness.recursive_candidate_search.agent2_round import invoke_agent2_candidate_search_round
from app.harness.recursive_candidate_search.cache import (
    FileCalibrationEvidenceCache,
    cache_key_for,
    functional_evaluation_cache_key_for,
)
from app.harness.recursive_candidate_search.types import (
    CalibrationRunOutcome,
    CalibrationRunRecord,
    FunctionalEvaluationRunOutcome,
    FunctionalEvaluationRunRecord,
    OrchestrationPolicy,
    RecursiveCandidateSearchResult,
    RoundRecord,
    StoppingReason,
)
from app.harness.version import RECURSIVE_CANDIDATE_SEARCH_POLICY_VERSION

CalibrationRequestProvider = Callable[..., dict[str, Any] | None]
InvokeRoundCallable = Callable[..., dict[str, Any]]
CalibrationRunnerCallable = Callable[..., dict[str, Any]]
FunctionalEvaluationRunnerCallable = Callable[..., dict[str, Any]]


def _extract_agent4_run_id(evaluation: dict[str, Any]) -> str | None:
    for ref in evaluation.get("provenance_refs", []):
        if isinstance(ref, str) and ref.startswith("agent4-report::"):
            return ref[len("agent4-report::") :]
    return None


def _extract_agent3_report_id(evaluation: dict[str, Any]) -> str | None:
    for ref in evaluation.get("provenance_refs", []):
        if isinstance(ref, str) and ref.startswith("agent3-report::"):
            return ref[len("agent3-report::") :]
    return None


def _structures(retained: list[dict[str, Any]]) -> frozenset[tuple[str, ...]]:
    return frozenset(tuple(sorted(c["module_ids"])) for c in retained)


def run_recursive_candidate_search(
    *,
    agent1_view_path: str | Path,
    criteria_weights: dict[str, Any],
    search_policy: dict[str, Any],
    calibration_selection_policy: dict[str, Any],
    orchestration_policy: OrchestrationPolicy,
    calibration_request_provider: CalibrationRequestProvider,
    stage_dir: str | Path,
    correlation_id: str,
    run_id_prefix: str,
    seed_modularization_id: str | None = None,
    submodel_module_id: str | None = None,
    exclude_single_module_from_ranking: bool = True,
    apply_resolution_correction: bool = False,
    build_request_path: str | Path | None = None,
    invoke_round: InvokeRoundCallable = invoke_agent2_candidate_search_round,
    calibration_runner: CalibrationRunnerCallable = run_module_calibration_workflow,
    cache: FileCalibrationEvidenceCache | None = None,
    timeout_seconds: float = 300.0,
    functional_evaluation_selection_policy: dict[str, Any] | None = None,
    functional_evaluation_runner: FunctionalEvaluationRunnerCallable = (
        run_module_functional_evaluation_workflow
    ),
    functional_cache: FileCalibrationEvidenceCache | None = None,
    attach_modularization: dict[str, Any] | None = None,
) -> RecursiveCandidateSearchResult:
    """Run the bounded recursive loop: one Agent 2 candidate-search round, calibrate whatever
    that round's own gate selected (reusing cached evidence by stable identity where possible),
    feed the resulting evidence into the next round, and stop on the first stopping condition
    that applies (task instructions §6), reporting exactly which one.

    ``calibration_selection_policy["total_calibration_run_budget"]`` is the *total* across every
    round -- this function tracks real usage (``total_calibration_runs_used``, incremented only
    for a genuinely new Agent 3/Agent 4 round trip, never for a cache hit or a locally-resolved
    ``BOUNDARY_INADEQUATE``) and passes it back to Agent 2 each round as ``calibration_runs_
    used_so_far``, so Agent 2's own gate never over-selects against the true remaining budget.

    ``orchestration_policy.require_human_review=True`` stops after the first round, returning
    that round's own ranked/calibrated candidate set with ``requires_user_review=True`` (task
    instructions §7) -- never proceeding to a second round without an explicit, separate call.

    ``attach_modularization`` (Automatic Hierarchical Recursive Modularization increment,
    optional): forwarded unchanged to every round's own ``invoke_round`` call -- this function
    itself never interprets it (that is entirely ``run_agent2_candidate_search_round.py``'s own
    job, inside Agent 2's venv); see ``app.harness.hierarchical_recursion``, which is this
    parameter's one real caller.
    """
    stage_dir = Path(stage_dir)
    cache = (
        cache
        if cache is not None
        else FileCalibrationEvidenceCache(stage_dir / "calibration_cache")
    )

    functional_cache = (
        functional_cache
        if functional_cache is not None
        else FileCalibrationEvidenceCache(stage_dir / "functional_evaluation_cache")
    )

    accumulated_evidence: dict[frozenset[tuple[str, str]], dict[str, Any]] = {}
    accumulated_functional_evidence: dict[frozenset[tuple[str, str]], dict[str, Any]] = {}
    rounds: list[RoundRecord] = []
    total_candidates_seen = 0
    total_calibration_runs_used = 0
    total_functional_evaluations_used = 0
    best_score_so_far: Decimal | None = None
    previous_structures: frozenset[tuple[str, ...]] | None = None
    previous_candidate_ids: frozenset[str] | None = None
    stopping_reason = StoppingReason.MAX_ROUNDS
    requires_user_review = False
    warnings: list[str] = []
    model_id = ""

    for round_number in range(1, orchestration_policy.max_rounds + 1):
        evidence_payload = (
            [
                {"content_key": [list(pair) for pair in sorted(key)], "evaluation": evaluation}
                for key, evaluation in accumulated_evidence.items()
            ]
            if accumulated_evidence
            else None
        )

        functional_evidence_payload = (
            [
                {"content_key": [list(pair) for pair in sorted(key)], "evaluation": evaluation}
                for key, evaluation in accumulated_functional_evidence.items()
            ]
            if accumulated_functional_evidence
            else None
        )

        round_summary = invoke_round(
            agent1_view_path=agent1_view_path,
            criteria_weights=criteria_weights,
            search_policy=search_policy,
            calibration_selection_policy=calibration_selection_policy,
            seed_modularization_id=seed_modularization_id,
            submodel_module_id=submodel_module_id,
            calibration_evidence=evidence_payload,
            calibration_runs_used_so_far=total_calibration_runs_used,
            exclude_single_module_from_ranking=exclude_single_module_from_ranking,
            apply_resolution_correction=apply_resolution_correction,
            build_request_path=build_request_path,
            correlation_id=correlation_id,
            run_id=f"{run_id_prefix}::round{round_number}",
            stage_dir=stage_dir,
            timeout_seconds=timeout_seconds,
            functional_evaluation_selection_policy=functional_evaluation_selection_policy,
            functional_evaluations_used_so_far=total_functional_evaluations_used,
            functional_evaluation_evidence=functional_evidence_payload,
            attach_modularization=attach_modularization,
        )
        model_id = round_summary["model_id"]
        retained = round_summary["retained"]
        total_candidates_seen += len(retained) + len(round_summary["degenerate"])

        available_scores = [
            Decimal(c["overall_score"]) for c in retained if c["overall_score"] is not None
        ]
        best_overall_score = max(available_scores) if available_scores else None

        requests_by_key = {
            (entry["request"]["modularization_id"], entry["request"]["module_id"]): entry
            for entry in round_summary["calibration_requests"]
        }
        locally_resolved_by_key = {
            (entry["evaluation"]["modularization_id"], entry["evaluation"]["module_id"]): entry
            for entry in round_summary["locally_resolved_evidence"]
        }

        calibration_runs: list[CalibrationRunRecord] = []
        for decision in round_summary["calibration_decisions"]:
            if decision["outcome"] != "CALIBRATE":
                continue
            key = (decision["candidate_id"], decision["module_id"])
            content_key = frozenset((pair[0], pair[1]) for pair in decision["content_key"])

            locally_resolved = locally_resolved_by_key.get(key)
            if locally_resolved is not None:
                evaluation = locally_resolved["evaluation"]
                accumulated_evidence[content_key] = evaluation
                calibration_runs.append(
                    CalibrationRunRecord(
                        round_number=round_number,
                        candidate_id=decision["candidate_id"],
                        module_id=decision["module_id"],
                        cache_key=None,
                        outcome=CalibrationRunOutcome.LOCALLY_RESOLVED,
                        agent4_run_id=None,
                        reason="resolved locally by Agent 2 (BOUNDARY_INADEQUATE); no round trip",
                    )
                )
                continue

            envelope = requests_by_key.get(key)
            if envelope is None:
                continue  # defensive: a CALIBRATE decision always has a request or a local
                # resolution; see app.agent2.candidate_orchestration.round
            request = envelope["request"]
            cache_key = cache_key_for(
                decision["content_key"],
                request["boundary_ports"],
                request["calibration_dataset_references"],
            )
            cached = cache.get(cache_key)
            if cached is not None:
                accumulated_evidence[content_key] = cached
                calibration_runs.append(
                    CalibrationRunRecord(
                        round_number=round_number,
                        candidate_id=decision["candidate_id"],
                        module_id=decision["module_id"],
                        cache_key=cache_key,
                        outcome=CalibrationRunOutcome.REUSED_CACHED_EVIDENCE,
                        agent4_run_id=_extract_agent4_run_id(cached),
                        reason=(
                            "reused cached evidence (identical module structure/boundary/"
                            "dataset/policy versions)"
                        ),
                    )
                )
                continue

            calibration_request = calibration_request_provider(
                candidate_id=decision["candidate_id"],
                module_id=decision["module_id"],
                content_key=decision["content_key"],
                dataset_references=request["calibration_dataset_references"],
            )
            if calibration_request is None:
                calibration_runs.append(
                    CalibrationRunRecord(
                        round_number=round_number,
                        candidate_id=decision["candidate_id"],
                        module_id=decision["module_id"],
                        cache_key=cache_key,
                        outcome=CalibrationRunOutcome.NO_DATASET_AVAILABLE,
                        agent4_run_id=None,
                        reason="calibration_request_provider returned no dataset for this module",
                    )
                )
                continue

            try:
                evaluation = calibration_runner(
                    request,
                    calibration_request,
                    stage_dir=stage_dir,
                    timeout_seconds=timeout_seconds,
                )
            except ModuleCalibrationWorkflowError as exc:
                calibration_runs.append(
                    CalibrationRunRecord(
                        round_number=round_number,
                        candidate_id=decision["candidate_id"],
                        module_id=decision["module_id"],
                        cache_key=cache_key,
                        outcome=CalibrationRunOutcome.INFRASTRUCTURE_FAILURE,
                        agent4_run_id=None,
                        reason=str(exc),
                    )
                )
                continue

            accumulated_evidence[content_key] = evaluation
            cache.put(cache_key, evaluation)
            total_calibration_runs_used += 1
            calibration_runs.append(
                CalibrationRunRecord(
                    round_number=round_number,
                    candidate_id=decision["candidate_id"],
                    module_id=decision["module_id"],
                    cache_key=cache_key,
                    outcome=CalibrationRunOutcome.NEW_RUN_SUCCEEDED,
                    agent4_run_id=_extract_agent4_run_id(evaluation),
                    reason="new Agent 3/Agent 4 round trip succeeded",
                )
            )

        functional_requests_by_key = {
            (entry["request"]["modularization_id"], entry["request"]["module_id"]): entry
            for entry in round_summary.get("functional_evaluation_requests", [])
        }
        functional_locally_resolved_by_key = {
            (entry["evaluation"]["modularization_id"], entry["evaluation"]["module_id"]): entry
            for entry in round_summary.get("locally_resolved_functional_evidence", [])
        }

        functional_evaluation_runs: list[FunctionalEvaluationRunRecord] = []
        functional_decisions = (
            round_summary.get("functional_evaluation_decisions", [])
            if functional_evaluation_selection_policy is not None
            else []
        )
        for decision in functional_decisions:
            if decision["outcome"] != "EVALUATE":
                continue
            key = (decision["candidate_id"], decision["module_id"])
            content_key = frozenset((pair[0], pair[1]) for pair in decision["content_key"])

            locally_resolved = functional_locally_resolved_by_key.get(key)
            if locally_resolved is not None:
                evaluation = locally_resolved["evaluation"]
                accumulated_functional_evidence[content_key] = evaluation
                functional_evaluation_runs.append(
                    FunctionalEvaluationRunRecord(
                        round_number=round_number,
                        candidate_id=decision["candidate_id"],
                        module_id=decision["module_id"],
                        cache_key=None,
                        outcome=FunctionalEvaluationRunOutcome.LOCALLY_RESOLVED,
                        agent3_report_id=None,
                        reason=(
                            "resolved locally by Agent 2 (UNSUPPORTED_ANALYSIS/"
                            "INSUFFICIENT_TARGETS); no round trip"
                        ),
                    )
                )
                continue

            envelope = functional_requests_by_key.get(key)
            if envelope is None:
                continue  # defensive: an EVALUATE decision always has a request or a local
                # resolution; see app.agent2.candidate_orchestration.round
            request = envelope["request"]
            functional_cache_key = functional_evaluation_cache_key_for(
                decision["content_key"],
                request["boundary_species_ids"],
                request["perturbation_targets"],
            )
            cached = functional_cache.get(functional_cache_key)
            if cached is not None:
                accumulated_functional_evidence[content_key] = cached
                functional_evaluation_runs.append(
                    FunctionalEvaluationRunRecord(
                        round_number=round_number,
                        candidate_id=decision["candidate_id"],
                        module_id=decision["module_id"],
                        cache_key=functional_cache_key,
                        outcome=FunctionalEvaluationRunOutcome.REUSED_CACHED_EVIDENCE,
                        agent3_report_id=_extract_agent3_report_id(cached),
                        reason=(
                            "reused cached evidence (identical module structure/boundary "
                            "species/perturbation battery/policy versions)"
                        ),
                    )
                )
                continue

            try:
                evaluation = functional_evaluation_runner(
                    request, stage_dir=stage_dir, timeout_seconds=timeout_seconds
                )
            except ModuleFunctionalEvaluationWorkflowError as exc:
                functional_evaluation_runs.append(
                    FunctionalEvaluationRunRecord(
                        round_number=round_number,
                        candidate_id=decision["candidate_id"],
                        module_id=decision["module_id"],
                        cache_key=functional_cache_key,
                        outcome=FunctionalEvaluationRunOutcome.INFRASTRUCTURE_FAILURE,
                        agent3_report_id=None,
                        reason=str(exc),
                    )
                )
                continue

            accumulated_functional_evidence[content_key] = evaluation
            functional_cache.put(functional_cache_key, evaluation)
            total_functional_evaluations_used += 1
            functional_evaluation_runs.append(
                FunctionalEvaluationRunRecord(
                    round_number=round_number,
                    candidate_id=decision["candidate_id"],
                    module_id=decision["module_id"],
                    cache_key=functional_cache_key,
                    outcome=FunctionalEvaluationRunOutcome.NEW_RUN_SUCCEEDED,
                    agent3_report_id=_extract_agent3_report_id(evaluation),
                    reason="new Agent 3 round trip succeeded",
                )
            )

        rounds.append(
            RoundRecord(
                round_number=round_number,
                round_summary=round_summary,
                calibration_runs=tuple(calibration_runs),
                best_overall_score=str(best_overall_score)
                if best_overall_score is not None
                else None,
                functional_evaluation_runs=tuple(functional_evaluation_runs),
            )
        )

        if orchestration_policy.require_human_review:
            stopping_reason = StoppingReason.HUMAN_REVIEW_GATE
            requires_user_review = True
            break
        if total_candidates_seen >= orchestration_policy.max_total_candidates:
            stopping_reason = StoppingReason.CANDIDATE_BUDGET_EXHAUSTED
            break
        if (
            total_calibration_runs_used
            >= calibration_selection_policy["total_calibration_run_budget"]
        ):
            stopping_reason = StoppingReason.CALIBRATION_BUDGET_EXHAUSTED
            break
        if (
            functional_evaluation_selection_policy is not None
            and total_functional_evaluations_used
            >= functional_evaluation_selection_policy["total_functional_evaluation_budget"]
        ):
            stopping_reason = StoppingReason.FUNCTIONAL_EVALUATION_BUDGET_EXHAUSTED
            break
        if not retained:
            stopping_reason = StoppingReason.SEARCH_EXHAUSTED
            break

        current_structures = _structures(retained)
        current_ids = frozenset(c["candidate_id"] for c in retained)
        if previous_structures is not None:
            if current_ids == previous_candidate_ids:
                stopping_reason = StoppingReason.REPEATED_CANDIDATE_SET
                break
            if current_structures == previous_structures:
                stopping_reason = StoppingReason.STABLE_BOUNDARY_CONVERGENCE
                break
            if (
                best_score_so_far is not None
                and best_overall_score is not None
                and best_overall_score - best_score_so_far
                < Decimal(orchestration_policy.improvement_epsilon)
            ):
                stopping_reason = StoppingReason.NO_IMPROVEMENT
                break

        previous_structures = current_structures
        previous_candidate_ids = current_ids
        if best_overall_score is not None:
            best_score_so_far = (
                best_overall_score
                if best_score_so_far is None
                else max(best_score_so_far, best_overall_score)
            )

    return RecursiveCandidateSearchResult(
        orchestration_id=f"recursive-search::{run_id_prefix}",
        model_id=model_id,
        seed_modularization_id=seed_modularization_id or "",
        rounds=tuple(rounds),
        stopping_reason=stopping_reason,
        requires_user_review=requires_user_review,
        total_candidates_seen=total_candidates_seen,
        total_calibration_runs_used=total_calibration_runs_used,
        orchestration_policy=orchestration_policy,
        policy_version=RECURSIVE_CANDIDATE_SEARCH_POLICY_VERSION,
        warnings=tuple(warnings),
        total_functional_evaluations_used=total_functional_evaluations_used,
    )


__all__ = ["run_recursive_candidate_search"]
