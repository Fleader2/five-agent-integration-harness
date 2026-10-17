# Workbench <-> Harness Module-Validation Contract (Module-Level Agent5 Validation and Experimental Design increment)

## 1. Goal

A sixth, genuinely separate Workbench-facing contract -- distinct from `docs/07_workbench
_harness_contract.md`'s fixed five-agent `FULL_PIPELINE`, `docs/15_workbench_hierarchical
_recursion_contract.md`'s hierarchy search, `docs/16_workbench_module_simulation_contract.md`'s
module simulation, `docs/17_workbench_module_boundary_derivation_contract.md`'s boundary
derivation, and `docs/18_workbench_module_calibration_contract.md`'s module calibration -- so
the Workbench can ask this harness to validate one already-calibrated hierarchy module's own
frozen parameter estimates against independent held-out experimental data through Agent 2 then
Agent 5. Never Agent 3/Agent 4 (a prior, already-succeeded calibration's own report is reused,
never recomputed), never the whole root model.

## 2. Contract types

`app/harness/workbench_contracts.py` (additive):

* `WorkbenchModuleValidationRequest` -- `run_id`, `project_id`, `subproject_id`,
  `contract_version`, `attach_payload` (the module's own `HierarchyNodeRecord.attach_payload`,
  with its resolved boundary ports already merged in as `module_ports`, identical to
  `WorkbenchModuleCalibrationRequest`'s own field), `module_id`, `agent4_report` (the full,
  verbatim report dict a *prior, already-succeeded* module-calibration execution produced --
  Agent 3/Agent 4 are never re-invoked by this contract), `validation_request` (Agent 5's own
  `ValidationRequest` dict shape -- `request_id`/`validation_observations`/
  `candidate_experiments`/..., built and validated entirely by the Workbench),
  `agent1_organism_id`/`input_artifact_references` (identical dual-input convention),
  `correlation_id`/`notes`/`submitted_at`.
* `WorkbenchModuleValidationResult` -- `status`, `module_id`, `modularization_id`,
  `module_handoff` (the **full** materialized Agent2->Agent3 handoff dict), `agent5_report`
  (Agent 5's own full report, verbatim -- every `validation`/`generalization_findings`/
  `candidate_experiments`/`experiment_scores`/`experimental_design_findings` entry, never
  compressed), `error`/`summary`/`warnings`/`replayed`.
* `WorkbenchRunErrorCode.MODULE_VALIDATION_EXECUTION_FAILED` -- a malformed request, a
  validation observation naming a species the materialized module does not have, the target
  module having no eligible standalone executable artifact, or an Agent 2/5 subprocess
  failure.

`WORKBENCH_MODULE_VALIDATION_CONTRACT_VERSION = "workbench-module-validation-v1"`.

## 3. Canonical execution path

`scripts/run_workbench_module_validation_request.py` -> `app.harness
.module_validation_execution.run_module_validation_execution_workflow`, which routes through
two real subprocess stages -- **never three**:

1. `app.harness.module_simulation.materialize_module_handoff` (shared, extracted from that
   module's own prior inline logic by the Module-Level Agent4 Calibration increment) -- the
   identical Agent 2 materialization every module-scoped workflow in this family already uses.
2. `runners/run_agent5.py` via `app.harness.adapters.build_agent5_handoff` (unchanged, the same
   adapter `app.harness.pipeline`'s own whole-model stage4->stage5 transition already uses)
   with the Workbench's own `agent4_report` (a prior calibration's own frozen report, never
   recomputed) and `validation_request` dict passed straight through to Agent 5.

Before Agent 5 is invoked, every validation observation's `target_species_id` is checked
against the materialized module's own real species ids -- a request naming an unknown one is
rejected as `ModuleValidationExecutionWorkflowError`, never silently sent to Agent 5.

Idempotent replay by `run_id` (identical convention to every other contract in this family).

## 4. Deliberately a separate module from `module_calibration_execution.py`

`app.harness.module_validation_execution` reuses the same building blocks
(`materialize_module_handoff`, `build_agent5_handoff`, `runners/run_agent5.py`) without
touching `module_calibration_execution.py` or `module_calibration.py` at all. This workflow's
own request shape (`agent4_report` supplied directly by the caller, Agent 3/Agent 4 never
invoked) is structurally different from calibration's own (`calibration_request` built,
Agent3+Agent4 both invoked fresh) -- a parallel module is the correct shape, not a branch
inside the existing one.

## 5. Tests

`tests/harness/test_workbench_module_validation_contract.py` (12 tests): contract round-trip
serialization; contract-mismatch/invalid-stage1-input/malformed-request pre-flight rejections
(fast, no subprocess); an unknown-observation-species rejection; real, live end-to-end
invocations continuing directly from a *real* `module_calibration_execution.py` round trip
(never a hand-crafted `agent4_report`) into a real Agent2->Agent5 validation against a second,
independent set of synthetic observations -- confirming Agent 5 actually used the correctly-
fitted calibrated parameter, produced low residuals against the held-out data, that the
module-specific artifact (not the root's) was materialized, and idempotent replay. Full
harness suite: 219 passed (207 pre-existing + 12 new); lint and format clean
repository-wide.

## 6. Downstream: Workbench-side readiness, snapshot, and persistence

This contract materializes and validates; it has no notion of "immutable execution snapshot",
"calibration-run reference", or persisted validation history of its own. What happens around
one request/result -- requiring a valid prior calibration result for this exact module,
checking independence of validation data from calibration data, snapshotting the exact
resolved boundary ports/frozen calibrated parameters/validation configuration before the
harness is ever invoked, and persisting Agent 5's own report against a durable `RunRecord` --
is entirely the Workbench's own responsibility, documented in
`mechanistic-modeling-workbench/docs/10_module_level_agent5_validation.md`. This harness never
represents a validation *history* of its own.
