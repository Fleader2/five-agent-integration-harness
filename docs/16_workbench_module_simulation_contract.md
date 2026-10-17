# Workbench <-> Harness Module-Simulation Contract (Executable-Module Materialization increment)

## 1. Goal

A third, genuinely separate Workbench-facing contract -- distinct from both
`docs/07_workbench_harness_contract.md`'s own fixed five-agent `FULL_PIPELINE` and
`docs/15_workbench_hierarchical_recursion_contract.md`'s own hierarchy search -- so the
Workbench can ask this harness to simulate one already-accepted hierarchy module (not the
whole root model) through Agent 2 (re-materialize that module's own standalone executable
artifact) then Agent 3.

## 2. Contract types

`app/harness/workbench_contracts.py` (additive):

* `WorkbenchModuleSimulationRequest` -- `run_id`, `project_id`, `subproject_id`,
  `contract_version`, `attach_payload` (the exact `HierarchyNodeRecord.attach_payload` dict a
  prior hierarchical-recursion result already reported for this module, passed back verbatim),
  `module_id` (the target module within it), `agent1_organism_id`/`input_artifact_references`
  (identical dual-input convention), `correlation_id`/`notes`/`submitted_at`.
* `WorkbenchModuleSimulationResult` -- `status`, `module_id`, `modularization_id`,
  `module_handoff_summary` (model_id/species/reaction/parameter counts -- enough to confirm
  the *module's* own filtered artifact, not the root's, was what Agent 3 actually simulated),
  `agent3_report` (Agent 3's own full report dict, verbatim), `error`/`summary`/`warnings`/
  `replayed`.
* `WorkbenchRunErrorCode.MODULE_SIMULATION_FAILED` -- a malformed request, an Agent 2/Agent 3
  subprocess failure, or (most commonly) the target module having no eligible standalone
  executable artifact.

`WORKBENCH_MODULE_SIMULATION_CONTRACT_VERSION = "workbench-module-simulation-v1"`.

## 3. Canonical execution path

`scripts/run_workbench_module_simulation_request.py` -> `app.harness.module_simulation
.run_module_simulation_workflow`, which routes through two real subprocess stages:

1. `app/harness/runners/run_agent2_materialize_module_handoff.py` (Agent 2's own venv):
   rebuilds the canonical model deterministically, attaches `attach_payload`'s own
   modularization (the identical mechanism `run_agent2_candidate_search_round.py`'s own
   `--attach-modularization` already uses), and calls Agent 2's existing, unchanged
   `app.agent2.module_calibration.build_module_calibration_request` -- the same function
   Recursive Module Evaluation Orchestration already uses to hand a module to Agent 3 for
   calibration, reused here for simulation.
2. `run_agent3.py` (unchanged, the identical runner Stage 3 of `FULL_PIPELINE` and
   `app.harness.module_calibration` already invoke) -- Agent 3 receives exactly the module's
   own filtered handoff, never the root model's.

Idempotent replay by `run_id` (identical convention to every other contract in this family).

## 4. Boundary treatment is never fabricated

Agent 2's own `generate_module_artifacts` only produces a standalone, simulatable artifact
(`readiness=EXECUTABLE`) for a module carrying an explicit boundary-condition port
(`ModulePort.externally_controlled=True`) for species crossing its own boundary -- confirmed
directly (`tests/agent2/test_antimony_generation.py` in the sibling `agent2-antimony-builder`
repository). The hierarchical-recursion search's own `attach_payload` never includes this
(deciding boundary treatment is not that search's job), so a module reached purely through it
honestly comes back `VIEW_ONLY` -- a genuine, disclosed "not yet simulatable" outcome, not a
defect (see `test_real_run_rejects_a_module_with_no_boundary_treatment_cleanly`).

`run_agent2_materialize_module_handoff.py` therefore accepts an **optional**
`attach_payload["module_ports"]` key (`[{"port_id", "module_id", "species_id", "direction",
"externally_controlled", "initial_value", "unit"}, ...]`) -- never auto-derived or invented
here, only passed through when a caller (today: a test standing in for a future human-reviewer
or Agent4/5 increment) already knows the right boundary treatment.

## 5. `HierarchyNodeRecord.attach_payload` (new field, additive)

Every `HierarchyNodeRecord`/`HierarchyNodeSummary` now carries `attach_payload: dict | None` --
the exact payload used to materialize *that* node's own submodel (`None` for the root node and
for a node never actually materialized). Component ids inside it are always real,
whole-network ids (submodel materialization never renames/rehashes them), so this *one*
payload, attached directly to a freshly-rebuilt root model, is always sufficient to
re-materialize the exact module it names later -- no multi-level attach chain is ever needed,
regardless of how deep in a hierarchy the module originally came from. This is the one
disclosed, additive change to `app.harness.hierarchical_recursion` this increment required;
nothing about recursion/acceptance/scoring semantics changed.

## 6. Tests

`tests/harness/test_workbench_module_simulation_contract.py` (11 tests): contract round-trip
serialization; contract-mismatch/invalid-stage1-input/missing-artifact/malformed-request
pre-flight rejections (fast, no subprocess); one real, live end-to-end happy-path invocation
(hand-supplied boundary treatment on a hand-built two-module split of the synthetic fixture),
confirming the module's own scoped artifact (2 of the root's 3 reactions/parameters) -- not the
root's -- was what Agent 3 actually received, plus idempotent replay; and one real, live
end-to-end invocation against a genuine hierarchical-recursion result's own `attach_payload`
(no boundary treatment), confirming the clean, disclosed `MODULE_SIMULATION_FAILED` rejection.
Full harness suite: 175 passed (164 pre-existing + 11 new); lint clean repository-wide.
