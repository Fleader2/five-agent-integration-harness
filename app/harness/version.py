"""The harness's own contract version and the version matrix it checks at every boundary.

The harness never invents a version number of its own for an agent's contract -- every value
below was read directly from that agent's own committed ``version.py`` (or, for Agent 1, its
``app/agent1/types.py``) at the time this harness was built. A mismatch between an artifact's
own declared version and the value recorded here is exactly what ``app.harness.contracts``
detects and reports as ``WorkflowStatus.CONTRACT_MISMATCH`` -- never silently ignored, never
auto-upgraded.

**Five-Agent Workflow V1 Hardening increment:** Agents 3, 4, and 5 each previously declared
their own name (``"agent2-to-agent3-v1"``, ``"agent2-agent3-to-agent4-v1"``,
``"agent2-agent4-to-agent5-v1"``) for what was already the identical real Agent 2 downstream
artifact shape. All three now expect the one canonical ``AGENT2_DOWNSTREAM_CONTRACT_VERSION``
Agent 2's own ``app.agent2.pipeline`` emits (``"agent2-downstream-v1"``) -- the harness no
longer needs, and no longer performs, any re-stamping of this field anywhere
(``app.harness.adapters`` passes ``agent2_model`` through byte-for-byte unchanged at every
boundary).

**Contract-version matrix synchronization increment:** ``AGENT1_CONTRACT_VERSION``/
``AGENT2_EXPECTED_AGENT1_VERSION`` were stale at ``"1.5"`` -- Agent 1's own
``AGENT1_CONTRACT_VERSION`` was bumped to ``"1.6"`` by its KEGG NETWORK support increment
(additive ``networks``/``network_nodes``/``network_edges``/``network_perturbations``/
``network_pathways``/``network_diseases``/``network_publications`` fields on
``Agent1KnowledgePackage``, and ``networks: tuple[CuratedNetwork, ...]`` on
``Agent1CuratedKnowledgeView``), but this harness's own copy was never updated, causing a false
``CONTRACT_MISMATCH`` against Agent 1's real, current, live output
(``tests/harness/test_real_sce00061_workflow.py``). Verified directly against Agent 2's own
runtime code (not just its docstrings) that this is a false alarm, not a true incompatibility:
Agent 2's own ``AGENT1_HANDOFF_VERSION`` constant
(``agent2-antimony-builder/app/agent2/version.py``) is itself still textually ``"1.5"`` --
apparently never bumped alongside Agent 1's own increment --
but nothing in Agent 2's actual parsing code (``app.agent2.handoff.translate``) compares an
incoming ``contract_version`` against that constant at all; it only requires the field to be
present. Agent 2 has no ``networks`` field of its own and never reads one, so a real ``"1.6"``
payload (additive fields only, nothing removed or reshaped) parses into Agent 2's existing shape
exactly as before. The two are genuinely compatible today; only this harness's own copied
bookkeeping was wrong. Agent 2's own unbumped constant is Agent 2's repository to fix, not this
harness's, and is left alone here.

**Human-Readable Antimony Naming and Provenance Separation increment:**
``AGENT2_DOWNSTREAM_CONTRACT_VERSION`` bumped ``"agent2-downstream-v1"`` ->
``"agent2-downstream-v2"``, mirroring Agent 2's own real bump. Agent 2's generated Antimony
symbols now prefer a curated biological name over a bare id; this silently broke Agent 3's own
independent re-derivation of the old id-only naming rule (``app.agent3.antimony_ids``, now
removed from that repository). Antimony symbol assignment is Agent 2-owned data: the new
``antimony_symbol_map`` field on the downstream handoff is Agent 2's own canonical-id ->
real-Antimony-symbol mapping, and Agent 3 now reads it directly at the ``agent2_to_agent3``
boundary instead of re-deriving a symbol. ``AGENT3_EXPECTED_AGENT2_VERSION``/
``AGENT4_EXPECTED_HANDOFF_VERSION``/``AGENT5_EXPECTED_HANDOFF_VERSION`` all update
automatically (each is an alias of ``AGENT2_DOWNSTREAM_CONTRACT_VERSION`` below, never a
separately-maintained copy).

**Agent 1 -> Agent 2 Biological Display Metadata Contract increment:** ``AGENT1_CONTRACT_
VERSION``/``AGENT2_EXPECTED_AGENT1_VERSION`` bumped ``"1.6"`` -> ``"1.7"``, mirroring Agent 1's
own real bump (additive ``genes``/``proteins`` fields on its handoff). This increment also
resolves the stale-constant technical debt the comment on ``AGENT2_EXPECTED_AGENT1_VERSION``
below used to disclose: Agent 2's own ``AGENT1_HANDOFF_VERSION`` constant, previously stuck
at ``"1.5"`` since Agent 1's Increment 3, is now also ``"1.7"`` -- genuinely current, not
merely tracked around here. ``AGENT2_CONTRACT_VERSION`` bumped ``"0.12"`` -> ``"0.13"`` to
match Agent 2's own real bump (``FullNetwork`` gained matching ``genes``/``proteins``
fields, ``ReactionSpecification`` gained ``ec_number``, ``ParameterSpecification`` gained
``substrate_id``) -- recorded here for traceability only, same as before, never itself
matrix-enforced.

**Explicit Enzyme Concentration Representation increment:** ``AGENT2_DOWNSTREAM_CONTRACT_
VERSION`` bumped ``"agent2-downstream-v2"`` -> ``"agent2-downstream-v3"``, mirroring Agent 2's
own real bump (``species[]`` gained ``source_protein_id``, ``kinetic_laws[]`` gained
``rate_law_scope`` -- both purely additive). ``AGENT3_EXPECTED_AGENT2_VERSION``/
``AGENT4_EXPECTED_HANDOFF_VERSION``/``AGENT5_EXPECTED_HANDOFF_VERSION`` all update
automatically (each is an alias below, never a separately-maintained copy) -- each of Agents
3, 4, and 5 bumped its own identical constant in step. ``AGENT2_CONTRACT_VERSION`` bumped
``"0.13"`` -> ``"0.14"`` to match Agent 2's own real bump (``SpeciesSpecification`` gained
``source_protein_id``, ``KineticLawSpecification`` gained ``rate_law_scope``) -- recorded here
for traceability only, same as before, never itself matrix-enforced.

**Recursive Module Evaluation Orchestration increment:** new ``app.harness.module_calibration``
module routes one Agent 2 candidate module (already converted into a standalone executable
Antimony submodel by Agent 2's own existing ``generate_module_artifacts`` path) through Agent 3
then Agent 4, and maps the result back into a structured ``ModuleCalibrationEvaluation`` dict for
Agent 2's own ``app.agent2.module_calibration``/``module_evaluation.calibration_adapter`` to
parse -- never Agent 2 calling Agent 4 directly. The module's own synthesized Agent2->Agent3
handoff dict declares the identical ``AGENT2_DOWNSTREAM_CONTRACT_VERSION`` a whole-model handoff
already does (Agent 3's own parser treats every field beyond ``antimony_text`` as optional, so
no new contract version or matrix row is needed for this boundary). New
``MODULE_CALIBRATION_WORKFLOW_POLICY_VERSION = "module-calibration-workflow-v1"`` versions this
module's own Agent4-``CalibrationStatus``-to-``ModuleCalibrationStatus`` mapping and field
derivation policy; no other version constant changes.

**Calibration Evidence Integration into Weight-Space Exploration increment:**
``MODULE_CALIBRATION_WORKFLOW_POLICY_VERSION`` bumped ``"module-calibration-workflow-v1"`` ->
``"module-calibration-workflow-v2"`` -- two real policy changes: (1) ``parameter_uncertainty``/
``parameter_correlations`` now pass through Agent 4's own newly-exposed ``standard_error``/
``parameter_correlations`` fields (``AGENT4_CONTRACT_VERSION`` ``"0.1"`` -> ``"0.2"`` on the
sibling repository) instead of disclosing them as always-unavailable, re-sorting each
correlation pair into canonical (``target_id_a < target_id_b``) order; (2) an Agent 3/Agent 4
subprocess crash or timeout now raises ``ModuleCalibrationWorkflowError`` (an infrastructure/
numerical failure) instead of being silently mapped to a disclosed ``CALIBRATION_FAILED``
result -- that previous behavior conflated "the harness/agent broke" with "the module itself
calibrates poorly," a real negative-evidence claim it had no basis to make. Never persisted as
a cached result either, so a retry after the underlying infrastructure problem is fixed is free
to actually re-run.

**Recursive Agent-4-Assisted Candidate Search Orchestration increment:** new ``app.harness
.recursive_candidate_search`` package -- the recursive loop this project's own prior increments
deliberately deferred. Drives Agent 2's own new ``app.agent2.candidate_orchestration`` one
bounded round at a time via a new subprocess runner
(``app/harness/runners/run_agent2_candidate_search_round.py``, the identical ``run_agent2.py``
convention), routes whatever that round's own calibration-selection gate selects through the
unchanged ``run_module_calibration_workflow``, reuses already-cached evidence by stable
identity (module content + boundary treatment + dataset references + Agent 3/4 contract/policy
versions, never by ``run_id``) across rounds *and* across separate orchestration invocations,
and applies an explicit, deterministic ``OrchestrationPolicy`` (max rounds, total candidate/
calibration-run budgets, a minimum-improvement threshold, stable-boundary/repeated-candidate-set
convergence, and an opt-in human-review gate that stops after one round). Agent 2 still never
calls Agent 3 or Agent 4 directly -- this package is the one, explicit routing point, exactly
like ``app.harness.module_calibration`` already is for a single module. New
``RECURSIVE_CANDIDATE_SEARCH_POLICY_VERSION = "recursive-candidate-search-v1"``, baked directly
into every cache key alongside ``MODULE_CALIBRATION_WORKFLOW_POLICY_VERSION``/
``AGENT3_CONTRACT_VERSION``/``AGENT4_CONTRACT_VERSION``; no other version constant changes.
"""

from __future__ import annotations

HARNESS_CONTRACT_VERSION = "0.2"

#: ``agent1-biochemical-curator/app/agent1/types.py`` -- ``AGENT1_CONTRACT_VERSION``.
AGENT1_CONTRACT_VERSION = "1.7"

#: Agent 1's own real, current, live ``AGENT1_CONTRACT_VERSION``. As of the Biological
#: Display Metadata increment this also matches Agent 2's own ``AGENT1_HANDOFF_VERSION``
#: constant (``agent2-antimony-builder/app/agent2/version.py``) -- no longer the stale,
#: unenforced drift this comment used to disclose (Agent 2's own constant was stuck at
#: ``"1.5"`` since Agent 1's Increment 3; both are now genuinely current).
AGENT2_EXPECTED_AGENT1_VERSION = "1.7"

#: ``agent2-antimony-builder/app/agent2/version.py`` -- ``AGENT2_CONTRACT_VERSION`` (Agent 2's
#: own ``ModelSpecification``/``FullAntimonyArtifact`` contract version -- not itself checked
#: by any downstream agent's handoff parser, but recorded for traceability).
AGENT2_CONTRACT_VERSION = "0.14"

#: ``agent2-antimony-builder/app/agent2/version.py`` -- ``AGENT2_DOWNSTREAM_CONTRACT_VERSION``.
#: The one canonical name Agent 2's own ``app.agent2.pipeline.run_agent2_pipeline`` emits, and
#: the single value every downstream boundary below now checks for.
AGENT2_DOWNSTREAM_CONTRACT_VERSION = "agent2-downstream-v3"

#: ``agent2-antimony-builder/app/agent2/build_request/types.py`` --
#: ``AGENT2_BUILD_REQUEST_CONTRACT_VERSION`` (Scoped-Build Support increment). Recorded here for
#: traceability only, like ``AGENT2_CONTRACT_VERSION`` above -- never matrix-enforced, because
#: this is an *input* artifact to Stage 2, not an output boundary a downstream stage consumes;
#: Agent 2's own ``build_request_from_dict`` is what actually checks a supplied
#: ``model_build_request`` artifact's own ``contract_version`` against it.
AGENT2_BUILD_REQUEST_CONTRACT_VERSION = "agent2-build-request-v1"

#: ``agent3-simulation-diagnostics/app/agent3/version.py`` -- ``AGENT2_HANDOFF_CONTRACT_VERSION``
#: (what Agent 3 itself expects the ``contract_version`` field to say).
AGENT3_EXPECTED_AGENT2_VERSION = AGENT2_DOWNSTREAM_CONTRACT_VERSION

#: ``agent3-simulation-diagnostics/app/agent3/version.py`` -- ``AGENT3_CONTRACT_VERSION``.
AGENT3_CONTRACT_VERSION = "0.1"

#: ``agent4-calibration-estimator/app/agent4/version.py`` -- ``AGENT4_HANDOFF_CONTRACT_VERSION``
#: (what Agent 4 itself expects the ``agent2_model.contract_version`` field to say).
AGENT4_EXPECTED_HANDOFF_VERSION = AGENT2_DOWNSTREAM_CONTRACT_VERSION

#: ``agent4-calibration-estimator/app/agent4/version.py`` -- ``AGENT4_CONTRACT_VERSION``.
AGENT4_CONTRACT_VERSION = "0.1"

#: ``agent5-validation-experimental-design/app/agent5/version.py`` --
#: ``AGENT5_HANDOFF_CONTRACT_VERSION`` (what Agent 5 itself expects the
#: ``agent2_model.contract_version`` field to say).
AGENT5_EXPECTED_HANDOFF_VERSION = AGENT2_DOWNSTREAM_CONTRACT_VERSION

#: ``agent5-validation-experimental-design/app/agent5/version.py`` -- ``AGENT5_CONTRACT_VERSION``.
AGENT5_CONTRACT_VERSION = "0.1"


#: One row per boundary this harness crosses: ``(boundary_name, artifact_field_path,
#: expected_value)``. ``artifact_field_path`` is a dotted path into the JSON artifact the
#: *producing* stage wrote, read by ``app.harness.contracts.check_contract_version`` before the
#: *consuming* stage is ever invoked.
CONTRACT_VERSION_MATRIX: tuple[tuple[str, str, str], ...] = (
    ("agent1_to_agent2", "contract_version", AGENT2_EXPECTED_AGENT1_VERSION),
    # Agent 3's own input artifact IS the agent2_model dict (no wrapping) -- Agent 4's/Agent
    # 5's own input artifacts wrap it under an "agent2_model" key alongside the other agent's
    # own report, per each one's documented handoff contract. All three now check for the
    # identical AGENT2_DOWNSTREAM_CONTRACT_VERSION value.
    ("agent2_to_agent3", "contract_version", AGENT3_EXPECTED_AGENT2_VERSION),
    ("agent2_agent3_to_agent4", "agent2_model.contract_version", AGENT4_EXPECTED_HANDOFF_VERSION),
    ("agent2_agent4_to_agent5", "agent2_model.contract_version", AGENT5_EXPECTED_HANDOFF_VERSION),
)

#: Recursive Module Evaluation Orchestration increment -- the version of
#: ``app.harness.module_calibration``'s own mapping policy (Agent 4 ``CalibrationStatus`` ->
#: ``ModuleCalibrationStatus``, fit-quality/identifiability-finding/boundary-sensitivity field
#: derivation). Bumped to v2 by the Calibration Evidence Integration into Weight-Space
#: Exploration increment (exposes Agent 4's own standard_error/parameter_correlations;
#: distinguishes an infrastructure/numerical subprocess failure from genuine negative
#: evidence).
MODULE_CALIBRATION_WORKFLOW_POLICY_VERSION = "module-calibration-workflow-v2"

#: Recursive Agent-4-Assisted Candidate Search Orchestration increment -- the version of
#: ``app.harness.recursive_candidate_search``'s own policy (the recursive-loop stopping rules,
#: the calibration-evidence cache-key shape, the Agent2-round subprocess contract this harness
#: drives). Baked directly into every cache key (``cache.cache_key_for``) alongside
#: ``MODULE_CALIBRATION_WORKFLOW_POLICY_VERSION``/``AGENT3_CONTRACT_VERSION``/
#: ``AGENT4_CONTRACT_VERSION`` -- bumping any of those automatically invalidates every
#: previously-cached entry.
RECURSIVE_CANDIDATE_SEARCH_POLICY_VERSION = "recursive-candidate-search-v1"

__all__ = [
    "AGENT1_CONTRACT_VERSION",
    "AGENT2_BUILD_REQUEST_CONTRACT_VERSION",
    "AGENT2_CONTRACT_VERSION",
    "AGENT2_DOWNSTREAM_CONTRACT_VERSION",
    "AGENT2_EXPECTED_AGENT1_VERSION",
    "AGENT3_CONTRACT_VERSION",
    "AGENT3_EXPECTED_AGENT2_VERSION",
    "AGENT4_CONTRACT_VERSION",
    "AGENT4_EXPECTED_HANDOFF_VERSION",
    "AGENT5_CONTRACT_VERSION",
    "AGENT5_EXPECTED_HANDOFF_VERSION",
    "CONTRACT_VERSION_MATRIX",
    "HARNESS_CONTRACT_VERSION",
    "MODULE_CALIBRATION_WORKFLOW_POLICY_VERSION",
    "RECURSIVE_CANDIDATE_SEARCH_POLICY_VERSION",
]
