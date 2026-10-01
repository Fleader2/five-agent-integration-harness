#!/usr/bin/env python3
"""Stage runner for Agent 2 -- executed with Agent 2's own venv interpreter, with
``cwd``/``PYTHONPATH`` set to Agent 2's own repository root.

Usage: ``run_agent2.py --input <agent1_view.json> --output <agent2_model.json>``

**Five-Agent Workflow V1 Hardening increment**: this is now a thin wrapper around Agent 2's own
canonical, official orchestration entrypoint, ``app.agent2.pipeline.run_agent2_pipeline`` --
the same function ``agent2-antimony-builder/scripts/run_agent2_pipeline.py`` wraps for direct
command-line use. The harness never duplicates Agent 2's own stage-sequencing logic; it only
invokes the one already-committed function that does.
"""

from __future__ import annotations

import argparse
import json


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    from app.agent2.pipeline import run_agent2_pipeline

    with open(args.input) as f:
        agent1_view = json.load(f)

    result = run_agent2_pipeline(agent1_view)

    with open(args.output, "w") as f:
        json.dump(result.downstream_handoff, f, indent=2)

    print(f"agent2_contract_version={result.downstream_handoff['contract_version']}")
    print(f"agent2_readiness={result.downstream_handoff['readiness']}")
    print(f"agent2_species_count={len(result.downstream_handoff['species'])}")
    print(f"agent2_reaction_count={len(result.downstream_handoff['reactions'])}")
    print(f"agent2_parameter_count={len(result.downstream_handoff['parameters'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
