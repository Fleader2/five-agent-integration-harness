#!/usr/bin/env python3
"""Stage runner for real Antimony-model inspection -- executed with Agent 3's own venv
interpreter (``antimony``/``roadrunner`` are Agent 3's own dependencies; nothing else in this
repository or the Workbench has them installed), with ``cwd``/``PYTHONPATH`` set to Agent 3's
own repository root, exactly like every other ``run_agent3*.py`` runner.

Usage: ``run_agent3_inspect_antimony_model.py --input <antimony_text.txt> --output
<result.json>``

Reads a plain Antimony source file and compiles it via Agent 3's own, already-committed
``app.agent3.loader.load_antimony_model`` -- never a second, re-implemented Antimony/RoadRunner
integration. Reports the real, compiled model's own species/compartment identifiers
(``roadrunner.RoadRunner.model.getFloatingSpeciesIds``/``getBoundarySpeciesIds``/
``getCompartmentIds``) -- this is the one authoritative ground truth a structural network's own
species list (Agent 2's own ``FullNetwork``) is never assumed to match exactly (Model-Species
Catalog Prerequisite increment, Workbench ``docs/26``): a species Agent 2's structural graph
names is not guaranteed to survive into the actually-compiled, loadable model, so this script's
own output -- never the structural network -- decides what belongs in a species catalog.

A compilation failure is reported as data (``load_succeeded: false``, ``load_message``), never
a non-zero exit for *that* reason -- this script's whole purpose is to report whether the model
loads, so a load failure is nonetheless a complete, successful inspection. A non-zero exit is
reserved for a genuine infrastructure defect (cannot even read the input file, an unexpected
exception from the loader itself).
"""

from __future__ import annotations

import argparse
import json


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    from app.agent3.loader import load_antimony_model

    with open(args.input) as f:
        antimony_text = f.read()

    result = load_antimony_model(antimony_text)

    if not result.succeeded:
        output = {
            "load_succeeded": False,
            "load_message": result.message,
            "floating_species_ids": [],
            "boundary_species_ids": [],
            "compartment_ids": [],
            "antimony_version": result.antimony_version,
            "roadrunner_version": result.roadrunner_version,
        }
    else:
        rr = result.roadrunner_instance
        assert rr is not None  # succeeded=True guarantees this, per ModelLoadResult's own contract
        output = {
            "load_succeeded": True,
            "load_message": None,
            "floating_species_ids": list(rr.model.getFloatingSpeciesIds()),
            "boundary_species_ids": list(rr.model.getBoundarySpeciesIds()),
            "compartment_ids": list(rr.model.getCompartmentIds()),
            "antimony_version": result.antimony_version,
            "roadrunner_version": result.roadrunner_version,
        }

    with open(args.output, "w") as f:
        json.dump(output, f, indent=2)

    print(f"load_succeeded={output['load_succeeded']}")
    print(f"floating_species_count={len(output['floating_species_ids'])}")
    print(f"boundary_species_count={len(output['boundary_species_ids'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
