#!/usr/bin/env python3
"""Stage runner for real Antimony-model inspection -- executed with Agent 3's own venv
interpreter (``antimony``/``roadrunner`` are Agent 3's own dependencies; nothing else in this
repository or the Workbench has them installed), with ``cwd``/``PYTHONPATH`` set to Agent 3's
own repository root, exactly like every other ``run_agent3*.py`` runner.

Usage: ``run_agent3_inspect_antimony_model.py --input <antimony_text.txt> --output
<result.json>``

Reads a plain Antimony source file and compiles it via Agent 3's own, already-committed
``app.agent3.loader.load_antimony_model`` -- never a second, re-implemented Antimony/RoadRunner
integration. Reports the real, compiled model's own species/compartment/parameter identifiers
(``roadrunner.RoadRunner.model.getFloatingSpeciesIds``/``getBoundarySpeciesIds``/
``getCompartmentIds``/``getGlobalParameterIds``) -- this is the one authoritative ground truth a
structural network's own species/parameter list (Agent 2's own ``FullNetwork``) is never
assumed to match exactly (Model-Species Catalog Prerequisite increment, Workbench ``docs/26``;
Joint Calibration Workflow prerequisite increment, Workbench ``docs/31``): a species or
parameter Agent 2's structural graph names is not guaranteed to survive into the actually-
compiled, loadable model, so this script's own output -- never the structural network --
decides what belongs in a species or parameter catalog.

**Independent vs. assignment-rule-derived parameters.** ``roadrunner.RoadRunner.model
.getGlobalParameterIds()`` reports every global parameter with no distinction between a
genuinely independent, settable constant and one whose value is actually computed by an SBML
assignment rule (e.g. Antimony's own ``Vmax := k1 * 2``) -- confirmed live:
``getAssignmentRuleIds`` is unusable from Python (a broken SWIG binding for its ``std::list&``
out-parameter, raises ``TypeError`` regardless of what is passed). The reliable mechanism is
one extra round trip through the model's own compiled SBML: ``rr.getCurrentSBML()``, parsed
with ``libsbml`` (already an installed dependency here -- RoadRunner itself depends on it; no
new dependency), then every ``Rule`` with ``isAssignment() is True`` names its own
``getVariable()`` as derived. A parameter in ``global_parameter_ids`` but *not* in
``assignment_rule_derived_parameter_ids`` is independent/settable; one that *is* in the latter
is a derived quantity and must never be treated as an independent calibration target.

A compilation failure is reported as data (``load_succeeded: false``, ``load_message``), never
a non-zero exit for *that* reason -- this script's whole purpose is to report whether the model
loads, so a load failure is nonetheless a complete, successful inspection. A non-zero exit is
reserved for a genuine infrastructure defect (cannot even read the input file, an unexpected
exception from the loader itself).
"""

from __future__ import annotations

import argparse
import json


def _assignment_rule_derived_parameter_ids(rr) -> list[str]:
    """Every global parameter id that is actually computed by an SBML assignment rule in the
    compiled model -- see module docstring for why this, not ``getAssignmentRuleIds``, is the
    reliable mechanism. Returns an empty list (never raises) if the current SBML cannot be
    re-parsed for any reason -- a defensive fallback only; a model that just successfully
    compiled via RoadRunner re-parsing as SBML through the identical library is not expected to
    fail in practice, but this script's own purpose (reporting whether/what loaded) must never
    be aborted by this secondary, best-effort classification."""
    try:
        import libsbml

        sbml_model = libsbml.readSBMLFromString(rr.getCurrentSBML()).getModel()
        return [
            sbml_model.getRule(i).getVariable()
            for i in range(sbml_model.getNumRules())
            if sbml_model.getRule(i).isAssignment()
        ]
    except Exception:  # defensive -- see docstring; never blocks the primary inspection result
        return []


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
            "global_parameter_ids": [],
            "assignment_rule_derived_parameter_ids": [],
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
            "global_parameter_ids": list(rr.model.getGlobalParameterIds()),
            "assignment_rule_derived_parameter_ids": _assignment_rule_derived_parameter_ids(rr),
            "antimony_version": result.antimony_version,
            "roadrunner_version": result.roadrunner_version,
        }

    with open(args.output, "w") as f:
        json.dump(output, f, indent=2)

    print(f"load_succeeded={output['load_succeeded']}")
    print(f"floating_species_count={len(output['floating_species_ids'])}")
    print(f"boundary_species_count={len(output['boundary_species_ids'])}")
    print(f"global_parameter_count={len(output['global_parameter_ids'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
