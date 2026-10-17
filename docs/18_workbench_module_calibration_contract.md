# Workbench <-> Harness Module-Calibration Contract (Module-Level Agent4 Calibration with Immutable Execution-Condition Provenance increment)

## 1. Goal

A fifth, genuinely separate Workbench-facing contract -- distinct from `docs/07_workbench
_harness_contract.md`'s fixed five-agent `FULL_PIPELINE`, `docs/15_workbench_hierarchical
_recursion_contract.md`'s hierarchy search, `docs/16_workbench_module_simulation_contract.md`'s
module simulation, and `docs/17_workbench_module_boundary_derivation_contract.md`'s boundary
derivation -- so the Workbench can ask this harness to calibrate one already-accepted
hierarchy module's own standalone executable artifact through Agent 2, Agent 3, then Agent 4
against Workbench-supplied experimental data. Never the whole root model, never Agent 2/3/4
code changed.

## 2. Contract types

`app/harness/workbench_contracts.py` (additive):

* `WorkbenchModuleCalibrationRequest` -- `run_id`, `project_id`, `subproject_id`,
  `contract_version`, `attach_payload` (the module's own `HierarchyNodeRecord.attach_payload`,
  with its resolved boundary ports already merged in as `module_ports`, identical to
  `WorkbenchModuleSimulationRequest`'s own field), `module_id`, `calibration_request` (Agent
  4's own `CalibrationRequest` dict shape -- `targets`/`observations`/`optimizer`/..., built
  and validated entirely by the Workbench), `agent1_organism_id`/`input_artifact_references`
  (identical dual-input convention), `correlation_id`/`notes`/`submitted_at`.
* `WorkbenchModuleCalibrationResult` -- `status`, `module_id`, `modularization_id`,
  `module_handoff` (the **full** materialized Agent2->Agent3 handoff dict, never a bare
  summary -- the Workbench's own immutable execution-snapshot persistence needs real
  parameter/initial-condition fidelity), `agent3_report` (verbatim), `agent4_report` (Agent 4's
  own full report, verbatim -- every `parameter_estimates`/`residuals`/
  `identifiability_findings` entry, never compressed the way `app.harness.module_calibration`'s
  own `ModuleCalibrationEvaluation` mapping does for its own, different consumer),
  `error`/`summary`/`warnings`/`replayed`.
* `WorkbenchRunErrorCode.MODULE_CALIBRATION_EXECUTION_FAILED` -- a malformed request, a
  calibration target/observation naming a parameter/species the materialized module does not
  have, the target module having no eligible standalone executable artifact, or an
  Agent 2/3/4 subprocess failure.

`WORKBENCH_MODULE_CALIBRATION_CONTRACT_VERSION = "workbench-module-calibration-v1"`.

## 3. Canonical execution path

`scripts/run_workbench_module_calibration_request.py` -> `app.harness
.module_calibration_execution.run_module_calibration_execution_workflow`, which routes through
three real subprocess stages:

1. `app.harness.module_simulation.materialize_module_handoff` (extracted from that module's own
   prior inline logic, now shared rather than duplicated) -- the identical Agent 2
   materialization `run_module_simulation_workflow` itself uses.
2. `runners/run_agent3.py` (unchanged, the same runner every other module-scoped workflow in
   this family already invokes).
3. `runners/run_agent4.py` via `app.harness.adapters.build_agent4_handoff` (unchanged, the same
   adapter `app.harness.module_calibration` itself already reuses) with the Workbench's own
   `calibration_request` dict passed straight through to Agent 4.

Before Agent 3/Agent 4 are invoked, every calibration target/observation is checked against the
materialized module's own real `parameters`/`species` ids -- a request naming an unknown one is
rejected as `ModuleCalibrationExecutionWorkflowError`, never silently sent to Agent 4.

Idempotent replay by `run_id` (identical convention to every other contract in this family).

## 4. Deliberately a separate module from `app.harness.module_calibration`

That module already routes one Agent2-*candidate* module through Agent 3 then Agent 4 for the
recursive hierarchy search's own scoring purposes, mapping Agent 4's own report down into a
compressed `ModuleCalibrationEvaluation` dict a scoring heuristic consumes. This contract's own
consumer (a Workbench end user wanting full calibration provenance for an already-durable,
already-accepted module) needs the opposite -- the complete, verbatim reports. Reusing the
existing mapping would silently drop exactly the fields the Workbench's own immutable-snapshot
persistence needs, so `app.harness.module_calibration_execution` instead reuses the same
underlying building blocks (`materialize_module_handoff`, `run_agent3.py`, `run_agent4.py`,
`build_agent4_handoff`) without ever touching `module_calibration.py` itself -- the recursive
hierarchy search's own calibration semantics are completely unchanged.

## 5. Tests

`tests/harness/test_workbench_module_calibration_contract.py` (13 tests): contract round-trip
serialization; contract-mismatch/invalid-stage1-input/malformed-request pre-flight rejections
(fast, no subprocess); an unknown-target-parameter rejection; real, live end-to-end invocations
against a hand-split two-module fixture with one species deliberately treated as an
externally-controlled fixed feed (beyond the one genuinely cross-module boundary species) --
confirming Agent 4 actually recovers a known true rate constant from analytically-generated
synthetic observations, that the module-specific artifact (not the root's) was materialized,
that the resolved boundary conditions are declared `const` in the actual Antimony text, idempotent
replay, and the clean, disclosed rejection of a module reached with no boundary treatment at
all. Full harness suite: 207 passed (194 pre-existing + 13 new); lint and format clean
repository-wide.

## 6. Downstream: Workbench-side validation, snapshot, and persistence

This contract materializes and calibrates; it has no notion of "immutable execution snapshot"
or persisted calibration history of its own. What happens around one request/result --
pre-flight validation against the module's own known membership, snapshotting the exact
resolved boundary ports/calibration configuration/referenced datasets before the harness is
ever invoked, and persisting Agent 4's own report against a durable `RunRecord` -- is entirely
the Workbench's own responsibility, documented in `mechanistic-modeling-workbench/docs
/09_module_level_agent4_calibration.md`. This harness never represents a calibration *history*
of its own.
