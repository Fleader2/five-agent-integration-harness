# Workbench <-> Harness Module-Boundary-Derivation Contract (Boundary-Condition Semantics increment)

## 1. Goal

A fourth, genuinely separate Workbench-facing contract -- distinct from `docs/07_workbench
_harness_contract.md`'s fixed five-agent `FULL_PIPELINE`, `docs/15_workbench_hierarchical
_recursion_contract.md`'s hierarchy search, and `docs/16_workbench_module_simulation_contract
.md`'s module simulation -- so the Workbench can ask this harness to derive *candidate*
boundary species for one already-accepted hierarchy module from Agent 2's own
reaction-participant topology. Reports structural candidates only -- never a treatment
decision, never a fabricated value; deciding what to *do* about a boundary species is entirely
the Workbench's own job (`app.orchestration.module_boundary_orchestrator` in that repository).

## 2. Contract types

`app/harness/workbench_contracts.py` (additive):

* `WorkbenchModuleBoundaryDerivationRequest` -- `run_id`, `project_id`, `subproject_id`,
  `contract_version`, `attach_payload` (the identical `HierarchyNodeRecord.attach_payload`
  dict `WorkbenchModuleSimulationRequest` already uses, passed back verbatim), `module_id`
  (the target module within it), `agent1_organism_id`/`input_artifact_references` (identical
  dual-input convention), `correlation_id`/`notes`/`submitted_at`.
* `WorkbenchModuleBoundaryDerivationResult` -- `status`, `module_id`, `candidates`
  (`[{"species_id", "direction"}, ...]` -- structural facts only), `error`/`summary`/
  `warnings`/`replayed`.
* `WorkbenchRunErrorCode.MODULE_BOUNDARY_DERIVATION_FAILED` -- a malformed request or an
  Agent 2 subprocess failure. Never produced for an empty candidate list (a module with no
  cross-boundary species is a genuine, disclosed, successful outcome).

`WORKBENCH_MODULE_BOUNDARY_DERIVATION_CONTRACT_VERSION =
"workbench-module-boundary-derivation-v1"`.

## 3. Canonical execution path

`scripts/run_workbench_module_boundary_derivation_request.py` -> `app.harness.module_boundary
_derivation.run_module_boundary_derivation_workflow`, which routes through one real subprocess
stage: `app/harness/runners/run_agent2_derive_boundary_candidates.py` (Agent 2's own venv).
Idempotent replay by `run_id` (identical convention to every other contract in this family).

## 4. The derivation algorithm is structural only

**No reusable Agent 2 function already computes "boundary species of module X from raw
topology"** -- confirmed by inspection: `app.agent2.modularization.derivation
.derive_cross_module_connections` only connects already-declared `ModulePort` rows, never
discovers one from topology; `app.agent2.submodel_materialization.closure
.compute_dependency_closure` computes a module's own dependency set, never which species are
*shared* with reactions outside it. `run_agent2_derive_boundary_candidates.py` therefore
replicates the small, pure graph computation `app.agent2.module_evaluation.criteria
.score_topological_separation` already performs internally for its own, unrelated scoring
purpose (reaction-id -> module-id membership, species-id -> participant-role usage) -- reading
only already-public `ModelSpecification`/`ModuleMembership`/`ReactionSpecification` fields,
never a new Agent 2 algorithm, never model construction.

A species is a boundary candidate of the target module if it is a participant of at least one
of the module's own member reactions *and* a participant of at least one reaction belonging to
a different module of the same modularization (or to no module at all). Direction is derived
structurally from the target module's own internal participant roles only: `REACTANT`/
`MODIFIER` in some internal reaction -> `INPUT`; `PRODUCT` -> `OUTPUT`; both -> `INPUT_OUTPUT`.
This is the only generalization the script makes -- a structural fact about which internal
reaction touches the species and how, never a guess about the species' own scientific boundary
treatment. Verified directly against a hand-split two-module fixture: species S3 (produced by
one module's own reaction, consumed by the other's) is correctly found as `OUTPUT` of the
first module and, symmetrically, `INPUT` of the second; the three fully-internal species never
appear as candidates of either.

## 5. Tests

`tests/harness/test_workbench_module_boundary_derivation_contract.py` (11 tests): contract
round-trip serialization; contract-mismatch/invalid-stage1-input/missing-artifact/malformed-
request pre-flight rejections (fast, no subprocess); real, live end-to-end invocations against
a hand-split two-module fixture confirming the correct single crossing species and its
correctly opposite direction from each module's own perspective, plus idempotent replay.
Full harness suite: 194 passed (183 pre-existing + 11 new); lint and format clean
repository-wide.

## 6. Downstream: Workbench-side resolution and execution-gating

This contract reports structural candidates only. What happens next -- persisting them,
recording a human's own treatment decision, computing a module's own execution readiness, and
gating `request_module_simulation` on it -- is entirely the Workbench's own responsibility,
documented in `mechanistic-modeling-workbench/docs/08_boundary_condition_semantics.md`. This
harness never represents a treatment decision or an execution-readiness status of its own.
