#!/usr/bin/env python3
"""Stage runner for whole-model Antimony-import fidelity auditing -- executed with Agent 2's
own venv interpreter, with ``cwd``/``PYTHONPATH`` set to Agent 2's own repository root, exactly
like every other ``run_agent2_*.py`` runner.

Calls Agent 2's own, pre-existing, unmodified ``app.agent2.antimony_import.import_antimony``
directly against caller-supplied Antimony text -- never Agent 1, never a structured network.
This is purely a fidelity audit (rule/event counts, which constructs were rejected and why):
the Workbench's own real executability check and species/parameter catalog capture come from
the wholly separate, Agent-3-only ``model_antimony_verification`` contract, reused unmodified;
this runner never duplicates that. Agent 2's own canonical ``ModelSpecification`` is read here
only for its structural counts -- never re-serialized or treated as a replacement artifact for
whatever Antimony text the caller originally supplied.

A disclosed, expected import outcome (malformed source, an unsupported construct, an ambiguous
module) is reported as data (``import_succeeded=False``, ``import_error_kind``, the real
exception message verbatim) -- never a non-zero exit for that reason. A non-zero exit is
reserved for a genuine infrastructure defect (cannot even read the input file, an unexpected
exception ``import_antimony`` itself guarantees never happens for an expected outcome).

Usage: ``run_agent2_import_antimony.py --input <request.json> --output <result.json>``
"""

from __future__ import annotations

import argparse
import json


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    from app.agent2.antimony_import import (
        ANTIMONY_IMPORT_PARSER_VERSION,
        AmbiguousAntimonyModuleError,
        MalformedAntimonySourceError,
        UnsupportedAntimonyConstructError,
        import_antimony,
    )
    from app.agent2.types import RuleType

    with open(args.input) as f:
        payload = json.load(f)

    output: dict
    try:
        model = import_antimony(payload["antimony_text"])
    except MalformedAntimonySourceError as exc:
        output = _failure("MALFORMED", str(exc))
    except UnsupportedAntimonyConstructError as exc:
        output = _failure("UNSUPPORTED_CONSTRUCT", str(exc))
    except AmbiguousAntimonyModuleError as exc:
        output = _failure("AMBIGUOUS_MODULE", str(exc))
    else:
        rule_counts = {RuleType.ASSIGNMENT: 0, RuleType.RATE: 0, RuleType.ALGEBRAIC: 0}
        for rule in model.rules:
            rule_counts[rule.rule_type] += 1
        output = {
            "import_succeeded": True,
            "import_error_kind": None,
            "import_message": None,
            "compartment_ids": [c.compartment_id for c in model.full_network.compartments],
            # Agent 2's own structural display name for each compartment (``is "..."``
            # directives; otherwise identical to the id) -- model_antimony_verification's own
            # Agent-3-side identity check has no notion of a compartment display name at all.
            "compartment_names": {
                c.compartment_id: c.name for c in model.full_network.compartments
            },
            "species_ids": [s.species_id for s in model.full_network.species],
            # Species-to-compartment context -- model_antimony_verification's own flat
            # species-id lists carry no compartment association; Agent 2's own structural
            # ``SpeciesSpecification.compartment_id`` is the one source for it on import.
            "species_compartment_ids": {
                s.species_id: s.compartment_id for s in model.full_network.species
            },
            "parameter_ids": [p.parameter_id for p in model.parameters],
            "reaction_ids": [r.reaction_id for r in model.full_network.reactions],
            "assignment_rule_count": rule_counts[RuleType.ASSIGNMENT],
            "rate_rule_count": rule_counts[RuleType.RATE],
            "algebraic_rule_count": rule_counts[RuleType.ALGEBRAIC],
            "event_count": len(model.events),
        }
    output["antimony_import_parser_version"] = ANTIMONY_IMPORT_PARSER_VERSION

    with open(args.output, "w") as f:
        json.dump(output, f, indent=2)

    print(f"import_succeeded={output['import_succeeded']}")
    if not output["import_succeeded"]:
        print(f"import_error_kind={output['import_error_kind']}")
    return 0


def _failure(kind: str, message: str) -> dict:
    return {
        "import_succeeded": False,
        "import_error_kind": kind,
        "import_message": message,
        "compartment_ids": [],
        "compartment_names": {},
        "species_ids": [],
        "species_compartment_ids": {},
        "parameter_ids": [],
        "reaction_ids": [],
        "assignment_rule_count": 0,
        "rate_rule_count": 0,
        "algebraic_rule_count": 0,
        "event_count": 0,
    }


if __name__ == "__main__":
    raise SystemExit(main())
