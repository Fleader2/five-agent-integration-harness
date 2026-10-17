#!/usr/bin/env python3
"""Stage runner for the Boundary-Condition Semantics increment -- executed with Agent 2's own
venv interpreter, with ``cwd``/``PYTHONPATH`` set to Agent 2's own repository root, exactly
like every other ``run_agent2_*.py`` runner.

Rebuilds the identical canonical ``ModelSpecification`` ``run_agent2.py`` would, attaches one
previously-accepted modularization (the identical ``--attach-modularization`` mechanism
``run_agent2_candidate_search_round.py``/``run_agent2_materialize_module_handoff.py`` already
use -- never duplicated or reimplemented here, only reused), and reports every *candidate*
boundary species crossing the target module's own boundary, purely from reaction-participant
topology -- never a treatment decision, never a fabricated value (task instructions §5).

**No reusable Agent 2 function computes this today** (confirmed by inspection: ``app.agent2
.modularization.derivation.derive_cross_module_connections`` only connects already-declared
``ModulePort`` rows, never discovers one from topology; ``app.agent2.submodel_materialization
.closure.compute_dependency_closure`` computes a module's own dependency set, never which
species are *shared* with reactions outside it). This script therefore replicates the small,
pure graph computation ``app.agent2.module_evaluation.criteria.score_topological_separation``
already performs internally for its own, unrelated scoring purpose (reaction-id -> module-id
membership, species-id -> reaction-ids usage) -- reading only already-public
``ModelSpecification``/``ModuleMembership``/``ReactionSpecification`` fields, never a new
Agent 2 algorithm, never model construction.

**Algorithm.** A species is a boundary candidate of the target module if it is a participant
of at least one of the module's own member reactions *and* a participant of at least one
reaction belonging to a different module of the same modularization (or to no module at all).
Direction is derived structurally from the target module's own internal participant roles
only: ``REACTANT`` (or ``MODIFIER``) in some internal reaction -> ``INPUT``; ``PRODUCT`` in
some internal reaction -> ``OUTPUT``; both -> ``INPUT_OUTPUT``. This is the only generalization
this script makes -- it is a structural fact about which internal reaction touches the species
and how, never a guess about the species' own scientific boundary treatment.

Usage: ``run_agent2_derive_boundary_candidates.py --input <agent1_view.json> --output
<candidates.json> --attach-modularization <json> --target-module-id ID
[--build-request <model_build_request.json>]``
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
    args = parser.parse_args()

    from dataclasses import replace

    from app.agent2.pipeline import run_agent2_pipeline
    from app.agent2.types import (
        ModelModularization,
        ModelModule,
        ModularizationMethod,
        ModuleComponentType,
        ModuleMembership,
        ParticipantRole,
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
    )

    target_module_id = args.target_module_id

    # reaction_id -> the one module_id (of this modularization) that owns it, if any.
    module_of_reaction: dict[str, str] = {
        m.component_id: m.module_id
        for m in model.module_memberships
        if m.modularization_id == attached_modularization_id
        and m.component_type is ModuleComponentType.REACTION
    }
    reactions_by_id = {r.reaction_id: r for r in model.full_network.reactions}

    target_reaction_ids = {
        rid for rid, mid in module_of_reaction.items() if mid == target_module_id
    }

    # For every boundary candidate species: which roles it plays in the target module's own
    # reactions (to derive direction), and whether it is also touched by a reaction belonging
    # to a different module (or no module at all) -- the structural boundary-crossing test.
    internal_roles: dict[str, set[ParticipantRole]] = {}
    crosses_boundary: set[str] = set()
    for reaction_id, reaction in reactions_by_id.items():
        is_internal = reaction_id in target_reaction_ids
        for participant in reaction.participants:
            if is_internal:
                internal_roles.setdefault(participant.species_id, set()).add(participant.role)
            else:
                owner = module_of_reaction.get(reaction_id)
                if owner != target_module_id:
                    # Touched by a reaction that is *not* part of the target module (a
                    # different module, or not covered by this modularization at all).
                    crosses_boundary.add(participant.species_id)

    candidates = []
    for species_id, roles in sorted(internal_roles.items()):
        if species_id not in crosses_boundary:
            continue
        is_reactant_or_modifier = bool(roles & {ParticipantRole.REACTANT, ParticipantRole.MODIFIER})
        is_product = ParticipantRole.PRODUCT in roles
        if is_reactant_or_modifier and is_product:
            direction = "INPUT_OUTPUT"
        elif is_product:
            direction = "OUTPUT"
        else:
            direction = "INPUT"
        candidates.append({"species_id": species_id, "direction": direction})

    with open(args.output, "w") as f:
        json.dump({"module_id": target_module_id, "candidates": candidates}, f, indent=2)

    print(f"boundary_candidate_count={len(candidates)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
