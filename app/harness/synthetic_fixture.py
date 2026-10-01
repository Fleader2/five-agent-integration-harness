"""Fixture-B-only post-processing: patching species initial concentrations and compartment
initial volume onto Agent 2's own real, live, canonical pipeline output.

**Why this exists**: no increment of the Agent 1 -> Agent 2 pipeline yet populates species
initial concentrations or compartment initial volume for ANY input -- a genuine, pre-existing,
disclosed upstream scope gap (also present on the real ``sce00061`` model; see Agent 3's own
``STEADY_STATE_NOT_FOUND`` diagnostic for that fixture). The real-yeast fixture (Fixture A)
accepts this gap as an honest, disclosed data limitation
(``WorkflowStatus.SUCCESS_WITH_EXPECTED_DATA_GAPS``). The synthetic fixture (Fixture B) exists
specifically to prove calibration/validation/experimental-design logic against a *known* ground
truth, which requires the model to actually simulate from the intended starting state -- so this
one, minimal, clearly-disclosed patch is applied, and only to this one fixture. It is harness-side
test infrastructure, never a change to Agent 2's own code, policy, or contract: every other field
of Agent 2's own real output (species/reactions/kinetic_laws/parameters/model structure) is
passed through completely unmodified.
"""

from __future__ import annotations

import copy
import re


def patch_initial_conditions(
    agent2_model: dict,
    *,
    concentrations_by_compound_id: dict[str, str],
    compartment_volumes: dict[str, str],
    volume_unit: str = "L",
) -> dict:
    """Return a new ``agent2_model`` dict (the input is never mutated) with:

    * ``species[].initial_concentration``/``initialization_source`` set for every species whose
      ``source_compound_id`` is a key of ``concentrations_by_compound_id``;
    * ``compartments[].initial_volume``/``volume_unit``/``constant`` set for every compartment
      whose ``compartment_id`` is a key of ``compartment_volumes``;
    * ``antimony_text`` rewritten with the matching initial-value assignments injected --
      otherwise the already-generated Antimony text (produced before this patch ever runs)
      would still declare these species/compartments with no initial value at all, and the
      JSON-level patch above would silently stop being true of the one artifact Agent 3/Agent 5
      actually simulate.

    Keyed by ``source_compound_id``/``compartment_id`` (Agent 2's own original curated ids),
    never by the generated, decorated ``species_id``/Antimony-internal variable name -- the
    robust field for this confirmed by directly inspecting a real canonical-pipeline output
    (``SpeciesSpecification.source_compound_id`` carries the original curated compound id
    unchanged).
    """
    model = copy.deepcopy(agent2_model)

    for species in model.get("species", []):
        compound_id = species.get("source_compound_id")
        if compound_id in concentrations_by_compound_id:
            species["initial_concentration"] = concentrations_by_compound_id[compound_id]
            species["initialization_source"] = "CURATED"

    for compartment in model.get("compartments", []):
        compartment_id = compartment.get("compartment_id")
        if compartment_id in compartment_volumes:
            compartment["initial_volume"] = compartment_volumes[compartment_id]
            compartment["volume_unit"] = volume_unit
            compartment["constant"] = True

    antimony_text = model["antimony_text"]

    species_id_by_compound_id = {
        s["source_compound_id"]: s["species_id"]
        for s in model.get("species", [])
        if s.get("source_compound_id") in concentrations_by_compound_id
    }
    species_local_var_by_species_id: dict[str, str] = {}
    for match in re.finditer(r"species\s+(\S+)\s+in\s+\S+;\s*//\s*species_id=(\S+)", antimony_text):
        local_var, species_id = match.group(1), match.group(2)
        species_local_var_by_species_id[species_id] = local_var

    compartment_local_var_by_id: dict[str, str] = {}
    for match in re.finditer(r"compartment\s+(\S+);\s*//\s*compartment_id=(\S+)", antimony_text):
        local_var, compartment_id = match.group(1), match.group(2)
        compartment_local_var_by_id[compartment_id] = local_var

    injected_lines: list[str] = []
    for compartment_id, volume in compartment_volumes.items():
        local_var = compartment_local_var_by_id.get(compartment_id)
        if local_var is not None:
            injected_lines.append(f"  {local_var} = {volume};")
    for compound_id, concentration in concentrations_by_compound_id.items():
        species_id = species_id_by_compound_id.get(compound_id)
        local_var = species_local_var_by_species_id.get(species_id) if species_id else None
        if local_var is not None:
            injected_lines.append(f"  {local_var} = {concentration};")

    if injected_lines:
        block = (
            "\n  // Five-Agent Workflow V1 Hardening increment: harness-side patched initial\n"
            "  // conditions (Fixture B only) -- see app.harness.synthetic_fixture.\n"
            + "\n".join(injected_lines)
            + "\n"
        )
        stripped = antimony_text.rstrip()
        if stripped.endswith("end"):
            antimony_text = stripped[: -len("end")] + block + "end\n"
        else:
            antimony_text = stripped + block
        model["antimony_text"] = antimony_text

    return model


#: The one, fixed ground-truth starting state for Fixture B's 4-species linear chain
#: (``S1 -> S2 -> S3 -> S4``) -- matches the pre-hardening hand-authored fixture's own ground
#: truth exactly, just keyed by the real curated compound ids this fixture's own
#: ``synthetic_agent1_view.json`` declares.
SYNTHETIC_GROUND_TRUTH_CONCENTRATIONS_BY_COMPOUND_ID: dict[str, str] = {
    "compound-S1": "10",
    "compound-S2": "0",
    "compound-S3": "0",
    "compound-S4": "0",
}
SYNTHETIC_GROUND_TRUTH_COMPARTMENT_VOLUMES: dict[str, str] = {"compartment-1": "1"}


def patch_synthetic_ground_truth_initial_conditions(agent2_model: dict) -> dict:
    """The one, fixed Fixture B post-processing step -- see module docstring."""
    return patch_initial_conditions(
        agent2_model,
        concentrations_by_compound_id=SYNTHETIC_GROUND_TRUTH_CONCENTRATIONS_BY_COMPOUND_ID,
        compartment_volumes=SYNTHETIC_GROUND_TRUTH_COMPARTMENT_VOLUMES,
    )


__all__ = [
    "SYNTHETIC_GROUND_TRUTH_COMPARTMENT_VOLUMES",
    "SYNTHETIC_GROUND_TRUTH_CONCENTRATIONS_BY_COMPOUND_ID",
    "patch_initial_conditions",
    "patch_synthetic_ground_truth_initial_conditions",
]
