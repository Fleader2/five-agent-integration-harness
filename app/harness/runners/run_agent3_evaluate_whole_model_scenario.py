#!/usr/bin/env python3
"""Stage runner for whole-model experimental-scenario evaluation -- executed with Agent 3's
own venv interpreter (``antimony``/``roadrunner`` are Agent 3's own dependencies), with
``cwd``/``PYTHONPATH`` set to Agent 3's own repository root, exactly like every other
``run_agent3*.py`` runner.

Usage: ``run_agent3_evaluate_whole_model_scenario.py --input <request.json> --output
<result.json>``

Reads a plain JSON request and evaluates it via Agent 3's own, already-committed
``app.agent3.scenario_evaluation.evaluate_scenario`` -- never a second, re-implemented
Antimony/RoadRunner integration. A scientific/request-validation outcome (model-load failure,
an unresolved identifier, a solver failure, numerical instability) is reported as data
(``evaluation_status``), never a non-zero exit for that reason -- a non-zero exit is reserved
for a genuine infrastructure defect (cannot even read the input file, an unexpected exception
from ``evaluate_scenario`` itself, which Agent 3's own docstring guarantees never happens for
an expected outcome).
"""

from __future__ import annotations

import argparse
import json


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    from app.agent3.scenario_evaluation import (
        ScenarioEvaluationRequest,
        StepIntervention,
        evaluate_scenario,
    )

    with open(args.input) as f:
        payload = json.load(f)

    request = ScenarioEvaluationRequest(
        request_id=payload["run_id"],
        parameter_overrides=dict(payload.get("parameter_overrides", {})),
        initial_value_overrides=dict(payload.get("initial_value_overrides", {})),
        interventions=tuple(
            StepIntervention(
                target_kind=iv["target_kind"],
                target_id=iv["target_id"],
                time=iv["time"],
                value=iv["value"],
            )
            for iv in payload.get("interventions", ())
        ),
        requested_times=tuple(payload["requested_times"]),
        requested_output_ids=tuple(payload["requested_output_ids"]),
        integrator=payload.get("integrator", "cvode"),
        absolute_tolerance=payload.get("absolute_tolerance", 1e-10),
        relative_tolerance=payload.get("relative_tolerance", 1e-8),
    )

    result = evaluate_scenario(payload["antimony_text"], request)

    output = {
        "evaluation_status": result.status.value,
        "predictions": (
            None
            if result.predictions is None
            else {k: list(v) for k, v in result.predictions.items()}
        ),
        "validation_errors": list(result.validation_errors),
        "solver_message": result.solver_message,
        "antimony_version": None,
        "roadrunner_version": result.engine_version,
    }

    with open(args.output, "w") as f:
        json.dump(output, f, indent=2)

    print(f"evaluation_status={output['evaluation_status']}")
    if output["predictions"] is not None:
        print(f"output_count={len(output['predictions'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
