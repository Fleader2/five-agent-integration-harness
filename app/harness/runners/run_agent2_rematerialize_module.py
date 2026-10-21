#!/usr/bin/env python3
"""Stage runner for the Module-Set Edited-Module Materialization increment -- executed with
Agent 2's own venv interpreter, with ``cwd``/``PYTHONPATH`` set to Agent 2's own repository
root, exactly like every other ``run_agent2_*.py`` runner.

Rebuilds the identical canonical ``ModelSpecification`` ``run_agent2.py`` would, attaches one
caller-supplied selection of ``REACTION`` memberships (the identical ``--attach-modularization``
mechanism ``run_agent2_materialize_module_handoff.py``/``run_agent2_derive_boundary_candidates
.py`` already use -- never duplicated or reimplemented here, only reused), and -- the one
genuinely new step this script adds -- calls Agent 2's own, pre-existing, unmodified
``app.agent2.submodel_materialization.materialize_submodel`` to correctly recompute the full
dependency closure (species/parameters/compartments/rules/events/observables) from exactly
that reaction selection, never trusting a stale or incomplete closure the caller might have
attached alongside it.

**Why this script exists and the other two don't suffice.** Neither
``run_agent2_materialize_module_handoff.py`` nor ``run_agent2_derive_boundary_candidates.py``
calls ``materialize_submodel``. The boundary-candidate script doesn't need to -- its own
algorithm reads reaction-participant topology directly from the rebuilt model's full network,
never from the attached closure, so it already works correctly for a reaction-only selection
with zero changes (confirmed by inspection, not assumed). The handoff script, however, passes
its attached memberships straight to ``build_module_calibration_request`` ->
``generate_module_artifacts``, which trusts whatever ``SPECIES``/``PARAMETER`` memberships it
is given verbatim, by component type, with no fallback for species at all -- correct only when
the caller's own attach payload already carries every closure member (true for every existing
caller, whose attach payload always comes from a real, already-materialized
``ModelModule.attach_payload``). A reaction-only selection would silently produce an artifact
built from a stale, possibly-wrong species/parameter set. Inserting ``materialize_submodel``
between "attach" and "build handoff" closes that gap -- it is the one function in this
repository that recomputes the closure fresh from reactions alone (``app.agent2
.submodel_materialization.closure.compute_dependency_closure``), already relied on by the
hierarchical-search process for exactly this reason (docs/38_canonical_submodel
_materialization.md).

Usage: ``run_agent2_rematerialize_module.py --input <agent1_view.json> --output
<result.json> --attach-modularization <json> --target-module-id ID --correlation-id ID
--run-id ID [--module-ports <json>] [--build-request <model_build_request.json>]``

``--attach-modularization`` is the identical JSON shape the other two scripts already use:
``{"modularization_id": str, "module_ids": [str, ...], "memberships": [{"module_id",
"component_type", "component_id"}, ...]}`` -- for this script's own caller, always REACTION-
type memberships only, naming the Workbench's own edited selection for one target module
(never species/parameters/rules/events/observables: this script, not the caller, is
responsible for deriving those correctly).

``--module-ports`` is deliberately optional and separate from ``--attach-modularization``'s own
(always absent) ``module_ports`` key -- the scientist's own resolved boundary treatments for
*this* reaction selection, supplied only once boundary review against the newly-derived
interfaces has happened (never the stale treatments from a different reaction selection, which
the caller is responsible for never passing here). Omitted or empty: the output reports the
materialized structure (species/reactions/parameters/lineage) with ``module_handoff: null`` --
a genuine "materialized, not yet simulatable" outcome, never an error.

Never mutates its own module membership beyond what ``--attach-modularization`` names: a
reaction's own kinetic law may require additional species/parameters/compartments (added to
the closure, exactly as ``materialize_submodel`` already does, deterministically, for any
caller), but no additional *reaction* is ever added -- the selected reaction set is exactly
what ``compute_dependency_closure`` treats as fixed input, never expanded.

Output JSON: ``{"module_id", "module_handoff": dict | null, "readiness_blocked_reason":
str | null, "lineage": {...}, "unresolved_dependencies": [...]}``.

Raises (propagates as a non-zero exit, exactly like every other ``run_agent2_*.py`` runner)
``app.agent2.submodel_materialization.errors.SubmodelMaterializationReferenceError`` for an
unknown ``modularization_id``/``module_id``, or a selection with zero ``REACTION``
memberships; plain ``ValueError`` (from ``compute_dependency_closure``) for a reaction id that
does not exist in the rebuilt model's own ``full_network.reactions`` at all -- an unknown
reaction id is never silently dropped or ignored.
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
    parser.add_argument("--module-ports", required=False, default=None)
    parser.add_argument("--correlation-id", required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()

    from dataclasses import replace
    from decimal import Decimal

    from app.agent2.module_calibration import build_module_calibration_request
    from app.agent2.module_calibration.errors import ModuleCalibrationReferenceError
    from app.agent2.pipeline import run_agent2_pipeline
    from app.agent2.submodel_materialization import materialize_submodel
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

    attached_ports: tuple = ()
    if args.module_ports is not None:
        with open(args.module_ports) as f:
            ports_data = json.load(f)
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
            for p in ports_data
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

    materialization_result = materialize_submodel(
        model, attached_modularization_id, args.target_module_id
    )
    submodel = materialization_result.submodel

    module_handoff = None
    readiness_blocked_reason = None
    try:
        request = build_module_calibration_request(
            submodel,
            materialization_result.submodel_modularization_id,
            materialization_result.submodel_module_id,
            correlation_id=args.correlation_id,
            run_id=args.run_id,
        )
        module_handoff = request.module_handoff
    except ModuleCalibrationReferenceError as exc:
        readiness_blocked_reason = str(exc)

    lineage = materialization_result.lineage
    output = {
        "module_id": args.target_module_id,
        "module_handoff": module_handoff,
        "readiness_blocked_reason": readiness_blocked_reason,
        "lineage": {
            "parent_model_id": lineage.parent_model_id,
            "parent_modularization_id": lineage.parent_modularization_id,
            "parent_module_id": lineage.parent_module_id,
            "submodel_modularization_id": lineage.submodel_modularization_id,
            "submodel_module_id": lineage.submodel_module_id,
            "retained_reaction_ids": list(lineage.retained_reaction_ids),
            "retained_species_ids": list(lineage.retained_species_ids),
            "retained_parameter_ids": list(lineage.retained_parameter_ids),
            "retained_compartment_ids": list(lineage.retained_compartment_ids),
            "explicit_enzyme_species_ids": list(lineage.explicit_enzyme_species_ids),
            "retained_rule_ids": list(lineage.retained_rule_ids),
            "retained_event_ids": list(lineage.retained_event_ids),
            "retained_observable_ids": list(lineage.retained_observable_ids),
            "materialization_policy_version": lineage.materialization_policy_version,
        },
        "unresolved_dependencies": [
            {
                "component_type": d.component_type,
                "component_id": d.component_id,
                "referenced_ids": list(d.referenced_ids),
                "reason": d.reason,
            }
            for d in materialization_result.unresolved_dependencies
        ],
    }

    with open(args.output, "w") as f:
        json.dump(output, f, indent=2)

    print(f"rematerialized_module_id={args.target_module_id}")
    print(f"retained_reaction_count={len(lineage.retained_reaction_ids)}")
    print(f"retained_species_count={len(lineage.retained_species_ids)}")
    print(f"module_handoff_present={module_handoff is not None}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
