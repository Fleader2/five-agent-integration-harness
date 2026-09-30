#!/usr/bin/env python3
"""Stage runner for the Agent 1 -> Agent 2 boundary -- executed with Agent 2's own venv
interpreter, with ``cwd``/``PYTHONPATH`` set to Agent 2's own repository root.

Usage: ``run_agent2.py --input <agent1_view.json> --output <translate_check_result.json>``

**Disclosed scope limitation** (see ``docs/01_orchestration_architecture.md`` §"The Agent 2
stage" and the completion report's own "remaining integration gaps" section): Agent 2's real
assembly pipeline is not one documented top-level entrypoint -- it is an internal, 11-plus-stage
composition (translate -> assemble_full_network -> resolve_enzyme_concentrations ->
build_enzyme_state_dynamics -> characterize_full_network -> assign_kinetic_laws ->
declare_parameters -> assess_boundaries -> decompose_network -> assemble_model_specification ->
generate_antimony, plus a reaction-context-resolution step whose exact position in that chain
was not independently confirmed). Hand-chaining all of this inside a harness runner script,
without an existing verified reference to copy, would risk the harness itself silently
re-implementing (and potentially mis-implementing) Agent 2's own internal logic -- exactly what
this harness's central rule forbids ("it does not duplicate agent logic").

This runner therefore exercises only the one cheap, safe, single-function, already-documented
piece of that boundary that IS a real top-level entrypoint:
``translate_agent1_view_to_agent2`` -- proving the *shape* of a given Agent 1 view is one Agent
2's own real contract parser accepts, without attempting the fragile multi-stage chain beyond
it. The harness's own Stage 2 *output artifact* for a given fixture is a separately-provided,
already-real, already-committed ``agent2_model`` JSON (see ``app.harness.pipeline`` for exactly
which file, and why), never a value this runner invents or silently repairs.
"""

from __future__ import annotations

import argparse
import json


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    from app.agent2.handoff.translate import translate_agent1_view_to_agent2

    with open(args.input) as f:
        view_data = json.load(f)

    try:
        contract = translate_agent1_view_to_agent2(view_data)
        result = {
            "translated": True,
            "contract_version": contract.contract_version,
            "reaction_count": len(contract.reactions),
            "message": None,
        }
    except Exception as exc:
        result = {
            "translated": False,
            "contract_version": None,
            "reaction_count": None,
            "message": f"{type(exc).__name__}: {exc}",
        }

    with open(args.output, "w") as f:
        json.dump(result, f, indent=2)

    print(f"agent2_translate_ok={result['translated']}")
    print(f"agent2_contract_version={result['contract_version']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
