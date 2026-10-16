#!/usr/bin/env python3
"""Stage runner for one round of Agent 2's own Recursive Agent-4-Assisted Candidate Search
Orchestration -- executed with Agent 2's own venv interpreter, with ``cwd``/``PYTHONPATH`` set
to Agent 2's own repository root, exactly like ``run_agent2.py``.

Rebuilds the identical canonical ``ModelSpecification`` ``run_agent2.py`` would (Agent 2's own
pipeline is deterministic -- the identical ``--input`` always reproduces the identical model),
then runs exactly one bounded, structurally-scored candidate-search round
(``app.agent2.candidate_orchestration.run_candidate_search_round``) under whatever calibration
evidence this round's own caller (always the harness's own recursive-loop driver) already has,
and writes back the one, narrow ``serialize_round_result`` dict a caller needs to drive the
next round or report provenance.

Usage: ``run_agent2_candidate_search_round.py --input <agent1_view.json> --output
<round_result.json> --criteria-weights <json> --search-policy <json>
--calibration-selection-policy <json> [--seed-modularization-id ID] [--submodel-module-id ID]
[--calibration-evidence <evidence.json>] [--calibration-runs-used-so-far N]
[--exclude-single-module-from-ranking true|false] [--apply-resolution-correction]
[--build-request <model_build_request.json>]
[--functional-evaluation-selection-policy <json>] [--functional-evaluations-used-so-far N]
[--functional-evaluation-evidence <evidence.json>] --correlation-id ID --run-id ID``

**Automatic Functional-Evaluation Selection and Caching increment:**
``--functional-evaluation-selection-policy`` mirrors ``--calibration-selection-policy`` exactly
but gates a real Agent 3 functional-evaluation round trip instead of an Agent 3/Agent 4
calibration round trip; omitted entirely (the default), this round produces zero functional-
evaluation decisions/requests, identical to every prior behavior.
"""

from __future__ import annotations

import argparse
import json
from decimal import Decimal


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--build-request", required=False, default=None)
    parser.add_argument("--seed-modularization-id", required=False, default=None)
    parser.add_argument("--submodel-module-id", required=False, default=None)
    parser.add_argument("--criteria-weights", required=True)
    parser.add_argument("--search-policy", required=True)
    parser.add_argument("--calibration-selection-policy", required=True)
    parser.add_argument("--calibration-evidence", required=False, default=None)
    parser.add_argument("--calibration-runs-used-so-far", required=False, default=0, type=int)
    parser.add_argument("--functional-evaluation-selection-policy", required=False, default=None)
    parser.add_argument("--functional-evaluations-used-so-far", required=False, default=0, type=int)
    parser.add_argument("--functional-evaluation-evidence", required=False, default=None)
    parser.add_argument(
        "--exclude-single-module-from-ranking",
        required=False,
        default="true",
        choices=("true", "false"),
    )
    parser.add_argument("--apply-resolution-correction", action="store_true")
    parser.add_argument("--correlation-id", required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()

    from app.agent2.candidate_orchestration import (
        build_submodel,
        run_candidate_search_round,
        serialize_round_result,
    )
    from app.agent2.candidate_orchestration.types import (
        CalibrationSelectionPolicy,
        FunctionalEvaluationSelectionPolicy,
    )
    from app.agent2.modularization_search.types import ProposalOperation, SearchPolicy
    from app.agent2.module_calibration.serialization import parse_module_calibration_evaluation
    from app.agent2.module_evaluation.types import (
        CriteriaWeights,
        CriterionWeight,
        ModularizationCriterion,
    )
    from app.agent2.module_functional_evaluation.serialization import (
        parse_module_functional_evaluation_result,
    )
    from app.agent2.pipeline import run_agent2_pipeline

    with open(args.input) as f:
        agent1_view = json.load(f)

    build_request = None
    if args.build_request is not None:
        from app.agent2.build_request import build_request_from_dict

        with open(args.build_request) as f:
            build_request = build_request_from_dict(json.load(f))

    pipeline_result = run_agent2_pipeline(agent1_view, build_request=build_request)
    model = pipeline_result.package.model_specification

    seed_modularization_id = args.seed_modularization_id
    if seed_modularization_id is None:
        if len(model.modularizations) == 1:
            seed_modularization_id = model.modularizations[0].modularization_id
        else:
            raise SystemExit(
                "run_agent2_candidate_search_round: model has "
                f"{len(model.modularizations)} modularizations -- --seed-modularization-id "
                "must be given explicitly"
            )

    if args.submodel_module_id:
        model, seed_modularization_id = build_submodel(
            model, seed_modularization_id, args.submodel_module_id
        )

    weights_data = json.loads(args.criteria_weights)
    weights = CriteriaWeights(
        weights=tuple(
            CriterionWeight(ModularizationCriterion(w["criterion"]), Decimal(w["weight"]))
            for w in weights_data["weights"]
        ),
        policy_version=weights_data["policy_version"],
    )

    search_policy_data = json.loads(args.search_policy)
    search_policy = SearchPolicy(
        max_iterations=search_policy_data["max_iterations"],
        max_candidates_per_iteration=search_policy_data["max_candidates_per_iteration"],
        beam_width=search_policy_data["beam_width"],
        allowed_operations=tuple(
            ProposalOperation(op) for op in search_policy_data["allowed_operations"]
        ),
        policy_version=search_policy_data["policy_version"],
    )

    selection_data = json.loads(args.calibration_selection_policy)
    selection_policy = CalibrationSelectionPolicy(
        max_candidates_per_generation=selection_data["max_candidates_per_generation"],
        max_modules_per_candidate=selection_data.get("max_modules_per_candidate"),
        score_threshold=(
            Decimal(selection_data["score_threshold"])
            if selection_data.get("score_threshold") is not None
            else None
        ),
        rank_threshold=selection_data.get("rank_threshold"),
        only_if_could_change_ordering=selection_data.get("only_if_could_change_ordering", False),
        total_calibration_run_budget=selection_data["total_calibration_run_budget"],
        policy_version=selection_data["policy_version"],
    )

    calibration_evidence = None
    if args.calibration_evidence:
        with open(args.calibration_evidence) as f:
            evidence_entries = json.load(f)
        calibration_evidence = {
            frozenset((pair[0], pair[1]) for pair in entry["content_key"]): (
                parse_module_calibration_evaluation(entry["evaluation"])
            )
            for entry in evidence_entries
        }

    functional_selection_policy = None
    if args.functional_evaluation_selection_policy:
        functional_data = json.loads(args.functional_evaluation_selection_policy)
        functional_selection_policy = FunctionalEvaluationSelectionPolicy(
            max_candidates_per_generation=functional_data["max_candidates_per_generation"],
            max_modules_per_candidate=functional_data.get("max_modules_per_candidate"),
            score_threshold=(
                Decimal(functional_data["score_threshold"])
                if functional_data.get("score_threshold") is not None
                else None
            ),
            rank_threshold=functional_data.get("rank_threshold"),
            only_if_could_change_ordering=functional_data.get(
                "only_if_could_change_ordering", False
            ),
            total_functional_evaluation_budget=functional_data[
                "total_functional_evaluation_budget"
            ],
            policy_version=functional_data["policy_version"],
        )

    functional_evaluation_evidence = None
    if args.functional_evaluation_evidence:
        with open(args.functional_evaluation_evidence) as f:
            functional_evidence_entries = json.load(f)
        functional_evaluation_evidence = {
            frozenset((pair[0], pair[1]) for pair in entry["content_key"]): (
                parse_module_functional_evaluation_result(entry["evaluation"])
            )
            for entry in functional_evidence_entries
        }

    round_result = run_candidate_search_round(
        model,
        seed_modularization_id,
        weights,
        search_policy,
        selection_policy,
        calibration_evidence=calibration_evidence,
        calibration_runs_used_so_far=args.calibration_runs_used_so_far,
        exclude_single_module_from_ranking=(args.exclude_single_module_from_ranking == "true"),
        apply_resolution_correction=args.apply_resolution_correction,
        functional_evaluation_selection_policy=functional_selection_policy,
        functional_evaluations_used_so_far=args.functional_evaluations_used_so_far,
        functional_evaluation_evidence=functional_evaluation_evidence,
        correlation_id=args.correlation_id,
        run_id=args.run_id,
    )

    with open(args.output, "w") as f:
        json.dump(serialize_round_result(round_result), f, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
