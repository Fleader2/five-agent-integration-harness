# Five-Agent End-to-End Integration Harness

## Overview

This repository orchestrates the five agents of the biochemical-modeling pipeline —
`agent1-biochemical-curator` → `agent2-antimony-builder` → `agent3-simulation-diagnostics` →
`agent4-calibration-estimator` → `agent5-validation-experimental-design` — across serialized
JSON contracts, and verifies the complete workflow operates correctly across repository
boundaries.

**Central rule:** the integration harness orchestrates existing agents; it does not duplicate
agent logic or silently repair their outputs.

Every agent runs as an isolated subprocess, in its own venv, with its own repository as `cwd`.
The harness's own code has **zero runtime dependencies** — it only reads/writes JSON files and
shells out.

Agent 2 is invoked through its own canonical orchestration entrypoint
(`app.agent2.pipeline.run_agent2_pipeline`) — a genuine, live subprocess call for both canonical
fixtures, never a copy of a pre-existing artifact. All five agents consume and produce the one
canonical `agent2-downstream-v1` contract for the Agent 2 boundary; nothing in this harness
re-stamps a contract version at any boundary.

See `docs/00_five_agent_workflow_v1_architecture.md` for the one-page system map (repository
roles, the contract/version matrix, and the V1 invariants), and `docs/01_orchestration_architecture.md`
through `docs/06_version1_success_criteria.md` for full detail — including the one disclosed
scope gap worth reading before trusting any run's own output: Agent 2's own pipeline does not yet
populate species initial concentrations or compartment initial volume for any input (see
`docs/01_orchestration_architecture.md`).

## Two canonical fixtures

* **Fixture A** — the real `sce00061` (yeast fatty-acid-biosynthesis) workflow. Expected result:
  `SUCCESS_WITH_EXPECTED_DATA_GAPS` (Agent 4/Agent 5 honestly report insufficient real data).
* **Fixture B** — a fully synthetic, known-ground-truth reaction chain. Expected result:
  `SUCCESS`, with Agent 4 genuinely recovering the two well-identified true parameters and
  flagging the deliberately-poorly-identified third, and Agent 5 genuinely ranking the
  known-informative next experiment at the top.

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"

.venv/bin/python3 scripts/run_fixture_a.py   # requires Agent 1's live database
.venv/bin/python3 scripts/run_fixture_b.py   # no external dependencies beyond the sibling venvs
```

See `docs/05_running_the_fixtures.md` for prerequisites and what each fixture proves.

## Workbench invocation

`scripts/run_workbench_request.py` is the canonical, documented entrypoint
for the `mechanistic-modeling-workbench` repository (or anything else) to
invoke this harness on behalf of a persisted project/subproject, with a
versioned request/result contract, idempotent replay by `run_id`, and
deterministic pre-flight rejections. It adds no new orchestration
mechanism -- it is a thin contract wrapper around the exact same
`run_workflow` the two fixture scripts above already call. See
`docs/07_workbench_harness_contract.md` for the full contract.

**Scoped-Build Support increment:** `input_artifact_references["model_build_request"]`,
when supplied, is forwarded unread to Agent 2's own runner as `--build-request`, which restricts
Agent 2's own assembled network to that `ModelBuildRequest`'s scope and reports any resulting
warning back through `WorkbenchRunResult.warnings`. The harness never parses the artifact's
content or applies any scoping itself. See `docs/07_workbench_harness_contract.md`'s own
"`ModelBuildRequest` -> Agent 2 scoped builds" section and
`agent2-antimony-builder/docs/20_scoped_build_support.md` for the full, canonical,
cross-repository record of this increment.

**Workbench Hierarchical Recursion Contract:** `scripts/run_workbench_hierarchical_request.py`
is a second, genuinely separate canonical entrypoint -- not the `FULL_PIPELINE` five-agent
workflow above, but a single Automatic Hierarchical Recursive Modularization search against a
model Agent 2 already assembled, with its own versioned request/result contract
(`WorkbenchHierarchicalInvocationRequest`/`WorkbenchHierarchicalRunResult`), the identical
idempotent-replay/pre-flight-rejection discipline, and a full per-node result set the Workbench
persists as a first-class record. See `docs/15_workbench_hierarchical_recursion_contract.md`
(resume), `docs/16_workbench_module_simulation_contract.md` (simulating one accepted
hierarchy module directly through Agent 2 then Agent 3, never the whole root model), and
`docs/17_workbench_module_boundary_derivation_contract.md` (deriving candidate boundary
species for one accepted hierarchy module from Agent 2's own reaction topology -- structural
facts only, never a treatment decision or a fabricated value), and
`docs/18_workbench_module_calibration_contract.md` (calibrating one accepted hierarchy
module's own standalone executable artifact through Agent 2, Agent 3, then Agent 4 against
Workbench-supplied experimental data, returning Agent 3's/Agent 4's own full, verbatim reports
rather than a compressed scoring-oriented mapping), and
`docs/19_workbench_module_validation_contract.md` (validating one already-calibrated
module's own frozen parameter estimates through Agent 2 then Agent 5 against independent
held-out data and recommending follow-up experiments -- Agent 3/Agent 4 are never re-invoked;
a prior, already-succeeded calibration's own report is reused as-is).

## Recursive Module Evaluation Orchestration

A separate, smaller, module-scoped boundary (`app/harness/module_calibration.py`) routes one
Agent 2 candidate module — already converted into a standalone executable Antimony submodel —
through Agent 3 then Agent 4, and maps the result into a structured, calibration-based
module-quality result for Agent 2's own Module Boundary Evaluation Framework. Agent 2 never
calls Agent 4 (or Agent 3) directly. See `docs/09_recursive_module_evaluation_orchestration.md`.

## Calibration Evidence Integration into Weight-Space Exploration

Fixes a real design flaw in the module above: an Agent 3/Agent 4 subprocess crash or timeout
(an infrastructure failure, never either agent's own disclosed outcome) is now raised as
`ModuleCalibrationWorkflowError` instead of being silently mapped into a disclosed
`CALIBRATION_FAILED` result — never persisted as a cached outcome. Also passes through Agent 4's
newly-exposed `standard_error`/`parameter_correlations` fields (re-sorting each correlation pair
into canonical order) instead of disclosing them as always-unavailable. See `docs/
10_calibration_evidence_integration_into_weight_space_exploration.md`.

## Recursive Agent-4-Assisted Candidate Search Orchestration

Closes the modularization loop: `app/harness/recursive_candidate_search` drives Agent 2's own
new candidate-search orchestration (`app.agent2.candidate_orchestration`) one bounded round at
a time via a new subprocess runner (`app/harness/runners/run_agent2_candidate_search_round.py`,
the identical `run_agent2.py` convention), routes whatever that round's own calibration-
selection gate selects through the unchanged `run_module_calibration_workflow`, reuses already-
cached evidence by stable identity (module content + boundary treatment + dataset references +
Agent 3/4 contract/policy versions — never by `run_id`) across rounds and across separate
orchestration invocations, and applies an explicit `OrchestrationPolicy` (max rounds, total
candidate/calibration-run budgets, a minimum-improvement threshold, stable-boundary/repeated-
candidate-set convergence, and an opt-in human-review gate that stops after one round and
returns `requires_user_review=True`). Agent 2 still never calls Agent 3 or Agent 4 directly —
this package is the one, explicit routing point. See `docs/
11_recursive_agent4_assisted_candidate_search_orchestration.md`.

## Functional Modularity Criteria from Agents 3 and 4

Mirrors the module-calibration orchestration above, but for Agent 3: `app.harness.module
_functional_evaluation` routes one candidate module's own functional-evaluation request (a
battery of deterministic perturbations spanning both inside and outside that module, against
the *whole* canonical network — never the module's own filtered standalone artifact) through a
new, focused Agent 3 runner (`app/harness/runners/run_agent3_functional_evaluation.py`, reusing
the existing, unchanged `run_agent3_pipeline`), and maps the result into a structured
`ModuleFunctionalEvaluationResult` for Agent 2's own `DYNAMIC_ISOLATION`/`SENSITIVITY_COHERENCE`
criteria. Agent 2 still never calls Agent 3 directly. See `docs/
12_functional_modularity_criteria_from_agents_3_and_4.md`.

## Automatic Functional-Evaluation Selection and Caching

Mirrors the recursive calibration-routing loop above with a second, genuinely separate one:
`app.harness.recursive_candidate_search`'s own orchestration loop now also routes whatever
Agent 2's new `FunctionalEvaluationSelectionPolicy` gate selects each round through
`app.harness.module_functional_evaluation` (unchanged), reusing cached evidence by stable
identity (`functional_evaluation_cache_key_for`: module content + boundary species +
perturbation-target battery + Agent 3 contract/policy versions) across rounds and across
separate orchestration invocations. Its own separate budget/stopping reason
(`FUNCTIONAL_EVALUATION_BUDGET_EXHAUSTED`) is independent of calibration's own -- a candidate
can be functionally evaluated without being calibrated, or vice versa. Agent 2 still never
calls Agent 3 directly. See `docs/13_automatic_functional_evaluation_selection_and_caching.md`.

## Automatic Hierarchical Recursive Modularization

A second recursion *dimension* on top of the flat loop above: `app.harness
.hierarchical_recursion.run_hierarchical_recursive_modularization` calls the unchanged
`run_recursive_candidate_search` once per hierarchy node (the root, then recursively one call
per module of each accepted modularization eligible for subdivision), reusing Agent 2's own
existing `materialize_submodel`/`build_submodel` via a new `run_agent2_candidate_search_round.py`
`--attach-modularization` flag that re-attaches a previously-accepted structure this harness
already received back -- never duplicating Agent 2's own search/evaluation logic. A child
decomposition is accepted only when it improves on the degenerate ("leave the parent module
intact") baseline by a configurable margin, under the identical structural/`DYNAMIC_ISOLATION`/
`SENSITIVITY_COHERENCE`/`CALIBRATION_INDEPENDENCE` weights already in effect. Every budget
(hierarchy nodes, functional evaluations, calibration runs) is tracked globally across the
whole run, never reset per branch, and the same calibration/functional-evidence caches are
shared across every level. See `docs/14_automatic_hierarchical_recursive_modularization.md`.

## Tests

```bash
.venv/bin/python3 -m pytest tests/ -q
```

The real-`sce00061` test module (`tests/harness/test_real_sce00061_workflow.py`) is skipped
automatically if Agent 1's live database is not reachable; every other test requires only the
five sibling repositories' own venvs to exist at the standard sibling-directory location.
