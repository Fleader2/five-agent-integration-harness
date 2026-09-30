#!/usr/bin/env python3
"""Stage runner for Agent 5 -- executed with Agent 5's own venv interpreter, with
``cwd``/``PYTHONPATH`` set to Agent 5's own repository root.

Usage: ``run_agent5.py --handoff <agent5_handoff.json> --request <validation_request.json>
--output <stage5_output.json>``
"""

from __future__ import annotations

import argparse
import dataclasses
import enum
import json


def _to_jsonable(obj):
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: _to_jsonable(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
    if isinstance(obj, enum.Enum):
        return obj.value
    if isinstance(obj, (list, tuple, set, frozenset)):
        return [_to_jsonable(v) for v in obj]
    if isinstance(obj, dict):
        return {k: _to_jsonable(v) for k, v in obj.items()}
    return obj


def _build_request(data: dict):
    from app.agent5.types import (
        CandidateExperiment,
        ExperimentType,
        ValidationObservation,
        ValidationObservationKind,
        ValidationObservationSet,
        ValidationRequest,
    )

    def _observation(o: dict) -> ValidationObservation:
        return ValidationObservation(
            observation_id=o["observation_id"],
            target_species_id=o["target_species_id"],
            kind=ValidationObservationKind(o["kind"]),
            time_points=tuple(o.get("time_points", ())),
            values=tuple(o["values"]),
            sigma=o.get("sigma"),
        )

    candidates = None
    if data.get("candidate_experiments") is not None:
        candidates = tuple(
            CandidateExperiment(
                experiment_id=c["experiment_id"],
                experiment_type=ExperimentType(c["experiment_type"]),
                target_id=c["target_id"],
                time_point=c.get("time_point"),
                perturbation_fraction=c.get("perturbation_fraction"),
                description=c.get("description", ""),
            )
            for c in data["candidate_experiments"]
        )

    return ValidationRequest(
        request_id=data["request_id"],
        validation_observations=ValidationObservationSet(
            observation_set_id=data["validation_observations"]["observation_set_id"],
            observations=tuple(
                _observation(o) for o in data["validation_observations"].get("observations", [])
            ),
        ),
        candidate_experiments=candidates,
        overfit_ratio_threshold=data.get("overfit_ratio_threshold", 3.0),
        max_default_candidates=data.get("max_default_candidates", 10),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--handoff", required=True)
    parser.add_argument("--request", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    from app.agent5.handoff import parse_agent5_handoff
    from app.agent5.pipeline import run_agent5_pipeline

    with open(args.handoff) as f:
        handoff_data = json.load(f)
    with open(args.request) as f:
        request_data = json.load(f)

    handoff = parse_agent5_handoff(handoff_data)
    request = _build_request(request_data)
    report = run_agent5_pipeline(handoff, request)

    with open(args.output, "w") as f:
        json.dump(_to_jsonable(report), f, indent=2, default=str)

    print(f"agent5_stage_status={report.overall_status.value}")
    print(f"agent5_n_experiment_scores={len(report.experiment_scores)}")
    print(f"agent5_sufficient_for_full_workflow={report.sufficient_for_full_workflow}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
