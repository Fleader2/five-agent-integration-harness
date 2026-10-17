#!/usr/bin/env python3
"""Stage runner for the Executable-Module Materialization increment -- executed with Agent 2's
own venv interpreter, with ``cwd``/``PYTHONPATH`` set to Agent 2's own repository root, exactly
like every other ``run_agent2_*.py`` runner.

Rebuilds the identical canonical ``ModelSpecification`` ``run_agent2.py`` would (Agent 2's own
pipeline is deterministic), attaches one previously-accepted modularization (the identical
``--attach-modularization`` mechanism ``run_agent2_candidate_search_round.py`` already uses --
never duplicated or reimplemented here, only reused), and builds one module's own standalone
Agent2->Agent3 handoff dict via Agent 2's own existing, unchanged
``app.agent2.module_calibration.build_module_calibration_request`` -- the identical function
Recursive Module Evaluation Orchestration already uses to hand a module to Agent 3 for
calibration, reused here for simulation instead.

Usage: ``run_agent2_materialize_module_handoff.py --input <agent1_view.json> --output
<module_handoff.json> --attach-modularization <json> --target-module-id ID --correlation-id ID
--run-id ID [--build-request <model_build_request.json>]``

``--attach-modularization`` names a JSON file (``{"modularization_id": str, "module_ids":
[str, ...], "memberships": [{"module_id": str, "component_type": str, "component_id": str},
...], "module_ports": [{"port_id", "module_id", "species_id", "direction",
"externally_controlled", "initial_value", "unit"}, ...] (optional)}``) describing a
previously-accepted modularization -- the ``modularization_id``/``module_ids``/``memberships``
always exactly the structure the harness already received back from an earlier
hierarchical-recursion call's own ``HierarchyNodeRecord.attach_payload`` (never invented or
re-derived here). Component ids inside it are always real, whole-network ids (submodel
materialization never renames/rehashes them), so this one payload, attached directly to the
freshly-rebuilt *root* model, is always sufficient to re-materialize the exact module it names
-- regardless of how deep in a hierarchy that module originally came from; no multi-level
replay is needed.

**``module_ports`` is deliberately optional and never auto-derived or invented here.** Agent 2's
own ``generate_module_artifacts`` only ever produces a standalone, simulatable artifact
(``readiness=EXECUTABLE``) for a module that carries an explicit boundary-condition port
(``ModulePort.externally_controlled=True``) for whatever species cross its own boundary --
never fabricated, per that function's own documented policy. The harness's own hierarchical-
recursion search does not (and, per task instructions, should not) decide boundary treatment
on a module's behalf, so a module reached purely through that search's own ``attach_payload``
(no ``module_ports`` entry) will correctly, honestly come back ``VIEW_ONLY`` -- a genuine,
disclosed "not yet simulatable without explicit boundary treatment" outcome, not a defect. A
caller that already knows (or has been told, e.g. by a human reviewer) the right boundary
treatment for a module may supply ``module_ports`` to make it simulatable.

Raises (propagates as a non-zero exit, exactly like every other ``run_agent2_*.py`` runner)
``app.agent2.module_calibration.errors.ModuleCalibrationReferenceError`` when
``--target-module-id`` has no eligible standalone artifact (``readiness`` is ``VIEW_ONLY``/
``NON_EXECUTABLE_UNRESOLVED_KINETICS``) -- a genuine, disclosed "this module cannot be
simulated" outcome, never silently turned into a request that could not actually be executed.
"""

from __future__ import annotations

import argparse
import json


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--build-request", required=False, default=None)
    parser.add_argument("--attach-modularization", required=True)
    parser.add_argument("--target-module-id", required=True)
    parser.add_argument("--correlation-id", required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()

    from dataclasses import replace
    from decimal import Decimal

    from app.agent2.module_calibration import build_module_calibration_request
    from app.agent2.pipeline import run_agent2_pipeline
    from app.agent2.types import (
        ModelModularization,
        ModelModule,
        ModularizationMethod,
        ModuleComponentType,
        ModuleMembership,
        ModulePort,
        ModulePortDirection,
    )

    with open(args.input) as f:
        agent1_view = json.load(f)

    build_request = None
    if args.build_request is not None:
        from app.agent2.build_request import build_request_from_dict

        with open(args.build_request) as f:
            build_request = build_request_from_dict(json.load(f))

    pipeline_result = run_agent2_pipeline(agent1_view, build_request=build_request)
    model = pipeline_result.package.model_specification

    with open(args.attach_modularization) as f:
        attach_data = json.load(f)
    attached_modularization_id = attach_data["modularization_id"]
    attached_module_ids = tuple(attach_data["module_ids"])
    attached_modules_by_id = {
        mid: ModelModule(module_id=mid, name=mid) for mid in attached_module_ids
    }
    attached_memberships = tuple(
        ModuleMembership(
            membership_id=(
                f"membership::{attached_modularization_id}::{m['module_id']}::"
                f"{m['component_type']}::{m['component_id']}"
            ),
            modularization_id=attached_modularization_id,
            module_id=m["module_id"],
            component_type=ModuleComponentType(m["component_type"]),
            component_id=m["component_id"],
        )
        for m in attach_data["memberships"]
    )
    attached_ports = tuple(
        ModulePort(
            port_id=p["port_id"],
            modularization_id=attached_modularization_id,
            module_id=p["module_id"],
            species_id=p["species_id"],
            direction=ModulePortDirection(p["direction"]),
            externally_controlled=bool(p.get("externally_controlled", False)),
            initial_value=(
                Decimal(p["initial_value"]) if p.get("initial_value") is not None else None
            ),
            unit=p.get("unit"),
        )
        for p in attach_data.get("module_ports", ())
    )

    merged_modules_by_id = {m.module_id: m for m in model.model_modules}
    merged_modules_by_id.update(attached_modules_by_id)
    model = replace(
        model,
        modularizations=(
            *model.modularizations,
            ModelModularization(
                modularization_id=attached_modularization_id,
                name=attached_modularization_id,
                method=ModularizationMethod.USER_DEFINED,
                module_ids=attached_module_ids,
            ),
        ),
        model_modules=tuple(merged_modules_by_id.values()),
        module_memberships=(*model.module_memberships, *attached_memberships),
        module_ports=(*model.module_ports, *attached_ports),
    )

    request = build_module_calibration_request(
        model,
        attached_modularization_id,
        args.target_module_id,
        correlation_id=args.correlation_id,
        run_id=args.run_id,
    )

    with open(args.output, "w") as f:
        json.dump(request.module_handoff, f, indent=2)

    print(f"module_handoff_contract_version={request.module_handoff['contract_version']}")
    print(f"module_handoff_species_count={len(request.module_handoff['species'])}")
    print(f"module_handoff_reaction_count={len(request.module_handoff['reactions'])}")
    print(f"module_handoff_parameter_count={len(request.module_handoff['parameters'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
