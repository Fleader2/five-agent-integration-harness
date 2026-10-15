#!/usr/bin/env python3
"""Stage runner for one Functional Modularity Criteria request -- executed with Agent 3's own
venv interpreter, with ``cwd``/``PYTHONPATH`` set to Agent 3's own repository root, exactly
like ``run_agent3.py``.

Unlike ``run_agent3.py`` (the full Version 1 whole-model pipeline, used by the main five-agent
workflow and never touched by this increment), this script runs *only* the perturbation battery
a caller explicitly supplies, against the identical, unchanged ``app.agent3.pipeline
.run_agent3_pipeline`` entrypoint (which already accepts an explicit ``perturbation_specs``
override) -- no new Agent 3 orchestration function, no new simulation algorithm.

Usage: ``run_agent3_functional_evaluation.py --input <functional_eval_input.json> --output
<agent3_report.json>``

``--input`` is a plain dict: ``{"agent2_model": <whole-network Agent2->Agent3 handoff dict>,
"baseline_request": {...SimulationRequest fields...}, "perturbation_specs": [{"target_kind":
..., "target_id": ..., "fraction": ...}, ...]}``.
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    from app.agent3.handoff import parse_agent2_handoff
    from app.agent3.pipeline import run_agent3_pipeline
    from app.agent3.types import PerturbationSpec, SimulationRequest

    with open(args.input) as f:
        data = json.load(f)

    handoff = parse_agent2_handoff(data["agent2_model"])
    baseline = data["baseline_request"]
    request = SimulationRequest(
        request_id=baseline["request_id"],
        start_time=baseline["start_time"],
        end_time=baseline["end_time"],
        num_points=baseline["num_points"],
        integrator=baseline.get("integrator", "cvode"),
        absolute_tolerance=baseline.get("absolute_tolerance", 1e-10),
        relative_tolerance=baseline.get("relative_tolerance", 1e-8),
    )
    specs = tuple(
        PerturbationSpec(
            target_kind=s["target_kind"], target_id=s["target_id"], fraction=s["fraction"]
        )
        for s in data["perturbation_specs"]
    )

    report = run_agent3_pipeline(
        handoff, request=request, perturbation_specs=specs, run_perturbations=True
    )

    with open(args.output, "w") as f:
        json.dump(_to_jsonable(report), f, indent=2)

    print(f"agent3_functional_evaluation_status={report.overall_status.value}")
    print(f"agent3_functional_evaluation_perturbation_count={len(report.perturbations)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
