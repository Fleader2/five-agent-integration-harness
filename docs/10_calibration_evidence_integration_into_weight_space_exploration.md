# Calibration Evidence Integration into Weight-Space Exploration

**Full design record** (evidence-mapping shape, weight-space behavior, Agent 4 field exposure,
example ranking change): `agent2-antimony-builder/docs/
32_calibration_evidence_integration_into_weight_space_exploration.md`. This document covers
only this harness's own side: the `app/harness/module_calibration.py` fix.

## What changed here

A real design flaw in the Recursive Module Evaluation Orchestration increment (`docs/
09_recursive_module_evaluation_orchestration.md`) is fixed: an Agent 3 or Agent 4 **subprocess
crash or timeout** was previously mapped straight into a disclosed
`ModuleCalibrationStatus.CALIBRATION_FAILED` result. Both agents' own pipelines are documented
to never raise for a genuine calibration/simulation outcome (`SIMULATION_FAILED`/
`OPTIMIZATION_FAILED` are always their own *disclosed* status values) -- so a non-zero
subprocess exit only ever means something actually broke (a bug, a missing dependency, a
timeout), never real evidence that the proposed module calibrates poorly. Conflating the two
meant an infrastructure problem could silently poison a module's own `CALIBRATION_INDEPENDENCE`
score with a fabricated negative finding.

`run_module_calibration_workflow` now raises `ModuleCalibrationWorkflowError` for this case
(alongside the pre-existing `INVALID_REQUEST` handling) -- **never persisted** as a cached
result, so a retry after the underlying infrastructure problem is fixed is free to actually
re-run rather than replaying a stale failure forever.

## Agent 4 field exposure, passed through unchanged in shape

`agent4-calibration-estimator` now exposes `ParameterEstimate.standard_error` and
`CalibrationResult.parameter_correlations` (previously-internal-only local covariance data --
no new calibration algorithm). `map_calibration_result_to_module_evaluation` now passes these
through into `ModuleCalibrationEvaluation.parameter_uncertainty`/`.parameter_correlations`
instead of disclosing them as always-unavailable. One detail this harness alone is responsible
for: Agent 4's own correlation pairs are in target *index* order, not necessarily lexicographic
-- `ModuleCalibrationEvaluation`'s own `ParameterCorrelationEstimate` requires
`target_id_a < target_id_b` (canonical pair ordering), so each pair is re-sorted here before
being handed to Agent 2, never left in whatever order Agent 4 happened to report it.

`MODULE_CALIBRATION_WORKFLOW_POLICY_VERSION` bumped `"module-calibration-workflow-v1"` ->
`"module-calibration-workflow-v2"` for both changes together.

## Tests

`tests/harness/test_module_calibration_workflow.py` (+2 tests):
`test_agent3_infrastructure_failure_raises_never_disclosed_as_evidence` (a malformed
`module_handoff` makes Agent 3's own `run_agent3.py` crash; asserts
`ModuleCalibrationWorkflowError` is raised and no result file is ever persisted) and
`test_map_exposes_standard_error_and_sorts_correlation_pairs` (confirms passthrough and
re-sorting). The pre-existing real round-trip test's own stale assertion ("standard_error is
always `None`") is corrected to assert the now-genuinely-available value instead. 83 passed
(full suite, including the real live-DB `sce00061` workflow); lint clean.
