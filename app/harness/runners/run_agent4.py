#!/usr/bin/env python3
"""Stage runner for Agent 4 -- executed with Agent 4's own venv interpreter, with
``cwd``/``PYTHONPATH`` set to Agent 4's own repository root.

Usage: ``run_agent4.py --handoff <agent4_handoff.json> --request <calibration_request.json>
--output <stage4_output.json>``

``--handoff`` is Agent 4's own two-key contract (``agent2_model``/``agent3_diagnostics``).
``--request`` is a plain dict matching ``CalibrationRequest``'s own shape (targets,
observations, optimizer config, authorizations) -- the harness builds this once per fixture
(see ``app.harness.pipeline``) and never varies it based on what Agent 4 reports back.
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
    from app.agent4.types import (
        CalibrationBounds,
        CalibrationRequest,
        CalibrationTarget,
        CalibrationTargetType,
        Observation,
        ObservationKind,
        ObservationPartition,
        ObservationSet,
        OptimizerConfig,
    )

    def _target(t: dict) -> CalibrationTarget:
        bounds = None
        if t.get("bounds") is not None:
            bounds = CalibrationBounds(lower=t["bounds"]["lower"], upper=t["bounds"]["upper"])
        return CalibrationTarget(
            target_kind=CalibrationTargetType(t["target_kind"]),
            target_id=t["target_id"],
            bounds=bounds,
            initial_guess=t.get("initial_guess"),
            prior_value=t.get("prior_value"),
            prior_weight=t.get("prior_weight", 0.0),
        )

    def _observation(o: dict) -> Observation:
        return Observation(
            observation_id=o["observation_id"],
            target_species_id=o["target_species_id"],
            kind=ObservationKind(o["kind"]),
            partition=ObservationPartition(o["partition"]),
            time_points=tuple(o.get("time_points", ())),
            values=tuple(o["values"]),
            sigma=o.get("sigma"),
        )

    optimizer_data = data.get("optimizer", {})
    return CalibrationRequest(
        request_id=data["request_id"],
        targets=tuple(_target(t) for t in data.get("targets", [])),
        observations=ObservationSet(
            observation_set_id=data["observations"]["observation_set_id"],
            observations=tuple(
                _observation(o) for o in data["observations"].get("observations", [])
            ),
        ),
        optimizer=OptimizerConfig(
            method=optimizer_data.get("method", "L-BFGS-B"),
            n_multistarts=optimizer_data.get("n_multistarts", 3),
            max_iterations=optimizer_data.get("max_iterations", 200),
            function_tolerance=optimizer_data.get("function_tolerance", 1e-10),
        ),
        authorized_provenance_classes=tuple(data.get("authorized_provenance_classes", ())),
        authorized_parameter_ids=tuple(data.get("authorized_parameter_ids", ())),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--handoff", required=True)
    parser.add_argument("--request", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    from app.agent4.handoff import parse_agent4_handoff
    from app.agent4.pipeline import run_agent4_pipeline

    with open(args.handoff) as f:
        handoff_data = json.load(f)
    with open(args.request) as f:
        request_data = json.load(f)

    handoff = parse_agent4_handoff(handoff_data)
    request = _build_request(request_data)
    report = run_agent4_pipeline(handoff, request)

    with open(args.output, "w") as f:
        json.dump(_to_jsonable(report), f, indent=2, default=str)

    print(f"agent4_stage_status={report.calibration.status.value}")
    print(f"agent4_n_estimates={len(report.calibration.parameter_estimates)}")
    print(f"agent4_sufficient_for_agent5={report.sufficient_for_agent5}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
