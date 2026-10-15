# Recursive Module Evaluation Orchestration

**Full design record** (request/result contracts, the `CALIBRATION_INDEPENDENCE` scoring
adapter, scope, remaining gaps): `agent2-antimony-builder/docs/
31_recursive_module_evaluation_orchestration.md`. This document covers only this harness's own
side: `app/harness/module_calibration.py`.

## What this is

A candidate module from Agent 2's unified modularization system can be converted into a
standalone executable Antimony submodel and routed through this harness to Agent 3
(simulation/diagnostics) then Agent 4 (calibration), producing a structured, calibration-based
module-quality result that flows back to Agent 2. **Agent 2 never calls Agent 4 (or Agent 3)
directly** — this harness is the one, explicit routing point.

This is a **separate, smaller, module-scoped boundary** from the existing whole-model
`run_workflow`/`WorkbenchInvocationRequest` pipeline (`app.harness.pipeline`) — it does not
extend `requested_entry_stage`, does not touch `CONTRACT_VERSION_MATRIX`, and reuses the
identical `AGENT2_DOWNSTREAM_CONTRACT_VERSION` a whole-model handoff already declares (Agent 3's
own parser already treats every field beyond `antimony_text` as optional, so a module's own
handoff dict is already a valid Agent2→Agent3 artifact by construction — zero code changes to
either Agent 3 or Agent 4 were needed).

## API

```python
from app.harness.module_calibration import run_module_calibration_workflow

result = run_module_calibration_workflow(
    request,              # a ModuleCalibrationRequest dict (built Agent2-side)
    calibration_request,  # a plain dict matching Agent 4's own CalibrationRequest shape
    stage_dir="artifacts/module-runs/<run_id>",
)
```

`request["module_handoff"]` must already be a complete Agent2→Agent3 handoff dict (built
Agent2-side by `app.agent2.pipeline.build_module_downstream_handoff`) — this harness treats it
as opaque and passes it to Agent 3 unchanged (`build_module_agent3_handoff` is pure
passthrough, never a reshape).

`map_calibration_result_to_module_evaluation` maps Agent 4's own `CalibrationStatus` to
`ModuleCalibrationStatus` (`SUCCESS`/`PARTIAL_SUCCESS` → `CALIBRATION_SUPPORTED`,
`UNIDENTIFIABLE` → `UNIDENTIFIABLE`, `INSUFFICIENT_DATA` → `INSUFFICIENT_DATA`,
`OPTIMIZATION_FAILED`/`SIMULATION_FAILED` → `CALIBRATION_FAILED`) and raises
`ModuleCalibrationWorkflowError` for `INVALID_REQUEST` (a request-construction defect, never a
disclosed calibration outcome).

## Persistence/replay

The result is written to `<stage_dir>/module_calibration_result_<run_id>.json`; a second call
with the identical `run_id` reads that file back verbatim rather than re-invoking either agent —
mirrors `scripts/run_workbench_request.py`'s own established replay pattern. Verified by test
(`tests/harness/test_module_calibration_workflow.py::test_persistence_replay_does_not_rerun_agents`)
that deletes the intermediate artifacts a real re-run would need before the second call.

## Tests

`tests/harness/test_module_calibration_workflow.py` — one real, full subprocess round trip
through Agent 3's then Agent 4's own real pipelines (a one-parameter exponential-decay module,
ground truth precomputed analytically with plain `math.exp`, no RoadRunner dependency inside
the test process itself) recovering the true decay rate within 5%; a persistence/replay test;
and fast, synthetic-dict unit tests for every `CalibrationStatus` → `ModuleCalibrationStatus`
mapping, `INVALID_REQUEST` raising, and boundary-sensitivity-finding category filtering.
Skipped automatically if Agent 3's or Agent 4's own sibling venv is not available, mirroring
this repository's existing skip convention for `test_real_sce00061_workflow.py`.
