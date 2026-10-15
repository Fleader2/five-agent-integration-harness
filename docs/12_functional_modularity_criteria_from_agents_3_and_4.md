# Functional Modularity Criteria from Agents 3 and 4

## 1. Goal

Route Agent 2's own new functional-evaluation requests (dynamic isolation / sensitivity
coherence evidence) through Agent 3, mirroring the existing module-calibration orchestration
exactly -- Agent 2 must not call Agent 3 directly.

## 2. Architecture

```text
candidate module
→ Agent 2's own functional-evaluation request (whole-network handoff + perturbation battery)
→ Harness (app.harness.module_functional_evaluation)
→ Agent 3 (a new, focused runner reusing the existing, unchanged run_agent3_pipeline)
→ functional evaluation result
→ Agent 2 module evaluator (DYNAMIC_ISOLATION / SENSITIVITY_COHERENCE)
```

`app.harness.module_functional_evaluation` mirrors `app.harness.module_calibration`'s own
structure field for field: `build_agent3_functional_evaluation_input` (passthrough, stripping
Agent 2's own `is_internal` tag, which Agent 3 never needs), `map_functional_result_to_module
_evaluation` (matches each requested target to its own Agent 3 result *positionally* -- the
existing, already-tested `run_perturbation_smoke_tests` ordering guarantee, never by re-
resolving names), and `run_module_functional_evaluation_workflow` (the one subprocess-routing
entry point, with the identical per-`run_id` persistence/replay convention as `run_module
_calibration_workflow`).

## 3. Why the whole network, never the module's own standalone artifact

Dynamic isolation and sensitivity coherence are properties of how a module behaves *relative to
its surrounding context* -- spillover, external dependence, and boundary capture cannot be
measured at all from a model that has been filtered down to the module alone, since there is no
"outside" left to measure against. `ModuleFunctionalEvaluationRequest.whole_network_handoff` is
therefore the identical, unfiltered canonical Agent2->Agent3 handoff the main five-agent
workflow already uses -- never module-scoped, unlike `ModuleCalibrationRequest`'s own
(correctly) filtered standalone artifact.

## 4. No new Agent 3 simulation algorithm

`app.agent3.pipeline.run_agent3_pipeline` already accepted an explicit `perturbation_specs`
override before this increment. The new, focused runner script
(`app/harness/runners/run_agent3_functional_evaluation.py`, mirroring `run_agent3.py`'s own
convention) calls it unchanged with Agent 2's own caller-supplied target battery, bypassing
only the unrelated diagnostic/steady-state reporting this boundary does not need. The one real
Agent 3-side change, `PerturbationResult.relative_change_by_species`, is purely additive --
exposing per-species data `run_perturbation` already computed internally and previously
discarded down to one scalar.

## 5. Evidence semantics (unchanged, extended)

An Agent 3 subprocess crash or timeout raises `ModuleFunctionalEvaluationWorkflowError` --
never cached, never mapped into a disclosed status, identical discipline to `Module
CalibrationWorkflowError`. A whole-network simulation that could not even load
(`overall_status="MODEL_LOAD_FAILED"`) maps to `UNSUPPORTED_ANALYSIS` -- disclosed, not an
error. Every other real, disclosed Agent 3 `SimulationStatus` per individual perturbation
(including a failed/unstable one) passes through on that perturbation's own
`PerturbationEffectRecord`, never silently dropped or treated as a zero effect.

## 6. Tests / lint

`tests/harness/test_module_functional_evaluation.py` (6 tests, mirroring `test_module
_calibration_workflow.py`'s own unit/integration split): one real, full round trip against a
genuine three-species chain (A -> B -> C), confirming a perturbation to the upstream rate
constant genuinely propagates to every downstream species while a perturbation to the
downstream rate constant leaves the upstream species' own relative change indistinguishable
from integrator noise (`< 1e-6`, contrasted against the real, large effect the upstream
perturbation produces) -- a genuine, checkable per-species propagation result, not a scalar
smoke test; persistence replay never re-invoking Agent 3; an infrastructure failure raising and
never being persisted; three unit tests for the mapping policy (passthrough shape,
`UNSUPPORTED_ANALYSIS` on whole-network load failure, and a defensive target/result
count-mismatch error). Full harness suite: 101 passed (95 pre-existing + 6 new); the real,
live `sce00061` five-agent workflow test is unaffected (untouched by this increment) and
unaffected by Agent 3's own additive field (confirmed via Agent 3's own 37-passed suite). Lint
clean.
