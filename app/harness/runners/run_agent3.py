#!/usr/bin/env python3
"""Stage runner for Agent 3 -- executed with Agent 3's own venv interpreter, with
``cwd``/``PYTHONPATH`` set to Agent 3's own repository root (see
``app.harness.subprocess_runner``'s own docstring for why this script never imports the
harness's own package).

Usage: ``run_agent3.py --input <agent2_model.json> --output <stage3_output.json>``

Reads a plain ``agent2_model``-shaped dict (Agent 3's own Version 1 handoff contract) and runs
Agent 3's own already-committed, already-validated pipeline against it unmodified. Never
retries, never alters the input, never invents a result if the real pipeline itself fails --
any exception here propagates to a non-zero exit code, which the harness reports as
``WorkflowStatus.AGENT_STAGE_FAILED``.
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

    with open(args.input) as f:
        data = json.load(f)

    handoff = parse_agent2_handoff(data)
    report = run_agent3_pipeline(handoff)

    with open(args.output, "w") as f:
        json.dump(_to_jsonable(report), f, indent=2)

    print(f"agent3_stage_status={report.overall_status.value}")
    print(f"agent3_diagnostics_count={len(report.diagnostics)}")
    print(f"agent3_sufficient_for_agent4={report.sufficient_for_agent4}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
