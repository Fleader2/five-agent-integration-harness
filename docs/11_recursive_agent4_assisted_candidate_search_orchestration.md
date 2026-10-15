# Recursive Agent-4-Assisted Candidate Search Orchestration

## 1. Goal

Close the modularization loop: allow promising candidate modularizations (produced by Agent 2's
own `search_candidate_modularizations`) to be calibrated through this harness, Agent 3, and
Agent 4, then use the returned `CALIBRATION_INDEPENDENCE` evidence to re-rank candidates and
continue a bounded search — without ever letting Agent 2 call Agent 4 (or Agent 3) directly.

## 2. Why this lives split across two repositories

Every agent repository in this project (including this harness) uses the identical top-level
package name `app`. Two of them can never be imported into the same Python process at once (see
`app.harness.subprocess_runner`'s own docstring) — so whichever process *decides how many rounds
to run and when to stop* cannot also be the process that holds a live, in-memory Agent 2
`ModelSpecification`. This increment therefore splits cleanly along that existing boundary,
mirroring the Recursive Module Evaluation Orchestration increment's own precedent exactly one
level up the stack:

- **Agent 2** (`app.agent2.candidate_orchestration`, in the sibling `agent2-antimony-builder`
  repository) owns everything that needs the real `ModelSpecification` object: candidate
  generation, structural scoring, the calibration-selection gate, and building the actual
  `ModuleCalibrationRequest`. It runs one bounded round at a time and returns, never calls
  anywhere else, and holds no state between calls.
- **This harness** (`app.harness.recursive_candidate_search`) owns the recursive loop itself:
  how many rounds to run, the cross-round calibration-evidence cache, routing every selected
  module through the unchanged `app.harness.module_calibration.run_module_calibration_workflow`,
  and every stopping rule.

Agent 2's own round function is invoked exactly like every other agent stage in this harness:
as an isolated subprocess, in Agent 2's own venv, via a new runner script
(`app/harness/runners/run_agent2_candidate_search_round.py`) that mirrors `run_agent2.py`'s own
convention byte for byte (`--input <agent1_view.json>` rebuilds the identical, deterministic
canonical model every round; Agent 2's own pipeline has no randomness anywhere).

## 3. The round-trip contract

Each round, this harness:

1. Serializes the calibration evidence accumulated across every prior round (keyed by a
   module's own content-addressed key, never by candidate id — exactly the content-addressing
   invariant Agent 2's own `app.agent2.modularization_search.identity` already established) to
   a JSON file.
2. Invokes `run_agent2_candidate_search_round.py`, which rebuilds the canonical model, runs one
   bounded `search_candidate_modularizations` call under that evidence, gates the result
   (`select_candidates_for_calibration`), and writes back `serialize_round_result`'s own,
   deliberately narrow dict — structural scores for every retained/degenerate candidate, every
   calibration decision with its own reason, every already-built `ModuleCalibrationRequest`
   needing a round trip, and every `BOUNDARY_INADEQUATE` evaluation Agent 2 already resolved
   locally.
3. For each `CALIBRATE` decision this harness checks its own cache (§4) before ever calling
   `run_module_calibration_workflow`; a cache miss requests a dataset from the caller-supplied
   `calibration_request_provider` (§5) and, if one exists, runs the real round trip.
4. Every resulting evaluation (new, reused, or locally resolved) is merged into the accumulated
   evidence for the *next* round's own input.

## 4. Caching and reuse

`cache.cache_key_for` builds one deterministic key from exactly the task's own named identity
components: the module's own content-addressed key, its declared boundary ports (species,
direction, `externally_controlled`), its calibration dataset references, and this harness's own
recorded Agent 3/Agent 4 contract/policy versions (`MODULE_CALIBRATION_WORKFLOW_POLICY_VERSION`/
`AGENT3_CONTRACT_VERSION`/`AGENT4_CONTRACT_VERSION`/`RECURSIVE_CANDIDATE_SEARCH_POLICY_VERSION`).
Two structurally identical modules, calibrated for two different candidates, or found again in a
later round, or even in a later, separate orchestration run against the same `stage_dir`, always
reuse the identical cached evidence — `FileCalibrationEvidenceCache` persists one JSON file per
key, independent of `run_id` (distinct from, and layered above,
`run_module_calibration_workflow`'s own, narrower per-`run_id` replay).

**Never caches an infrastructure failure.** A `ModuleCalibrationWorkflowError` (an Agent 3/Agent
4 subprocess crash or timeout) is recorded as `CalibrationRunOutcome.INFRASTRUCTURE_FAILURE` and
the cache is never written — the identical module is retried, never silently skipped, the next
time it is selected (confirmed by test).

## 5. Where the calibration dataset comes from

This harness never invents observation data. `calibration_request_provider` is always
caller-supplied: given a module's own candidate/module id, content key, and declared dataset
references, it returns the real Agent 4 `calibration_request` dict (targets/bounds/
observations) to use, or `None` when no dataset exists for it yet (recorded as
`CalibrationRunOutcome.NO_DATASET_AVAILABLE`, never attempted). Deciding *what* data to collect
for a module that currently has none is Agent 5's own future job (explicit non-goal here).

## 6. Stopping rules

`OrchestrationPolicy` names an explicit, deterministic limit for each condition the task
requires, checked in a fixed order every round: the human-review gate (§7) first, then the two
budgets (total candidates ever retained/degenerate across every round; total real calibration
runs), then structural convergence (an empty retained set; the identical retained candidate-id
set twice in a row; the identical retained *structural partition* twice in a row, by
`module_ids`, even under different candidate ids), then a minimum-improvement threshold on the
best retained `overall_score`, and finally `max_rounds` itself. `RecursiveCandidateSearchResult
.stopping_reason` always names exactly which one fired.

## 7. Human-in-the-loop gate

`OrchestrationPolicy.require_human_review=True` makes the very first round's own call the last
one: the loop stops immediately after that round with `stopping_reason=HUMAN_REVIEW_GATE` and
`requires_user_review=True`, returning that round's own ranked/calibrated candidate summaries
for a human to review before any further search or refinement is ever attempted. This project
never assumes fully automatic optimization is always wanted.

## 8. Evidence semantics (unchanged)

Every rule the prior increments established is reused, not re-implemented: `INSUFFICIENT_DATA`/
`BOUNDARY_INADEQUATE` are unavailable evidence; `CALIBRATION_FAILED`/`UNIDENTIFIABLE` are real,
available negative evidence; an Agent 3/Agent 4 infrastructure failure is an error, never a
module-quality score; the default calibration aggregation is `WEIGHTED_MEAN`; a one-module
candidate remains reference-only and excluded from ranking by default. Nothing in this
increment changes any of that — it only decides *when* to go get real evidence and *how long*
to keep refining once it has some.

## 9. Recursive readiness

`submodel_module_id`, threaded straight through to Agent 2's own `build_submodel`, lets this
exact procedure run against one already-decomposed module's own standalone `ModelSpecification`
instead of the whole canonical model — the same round contract, same cache, same stopping
rules, no code path change. Never triggered automatically: a caller must explicitly name the
module to recurse into (task instructions §5).

## 10. Tests / lint

`tests/harness/test_recursive_candidate_search.py` (20 tests, all fast/deterministic — an
injected fake `invoke_round`/`calibration_runner`, never a real subprocess call, mirroring
`test_module_calibration_workflow.py`'s own established unit/integration split): cache
determinism and sensitivity to boundary/dataset changes, cache reuse across rounds, a changed
boundary invalidating the cache, an infrastructure failure never being cached and being retried,
no-dataset-available skipping without ever calling the runner, a locally-resolved
`BOUNDARY_INADEQUATE` requiring no round trip, every named stopping reason, the human-review
gate, `submodel_module_id` threading, deterministic repeated execution, and an end-to-end
ranking reversal driven by fed-back calibration evidence. Full harness suite: 95 passed (75
pre-existing + 20 new); the real, live `sce00061` five-agent workflow test is unaffected (this
increment touches no code that test's own run exercises) and re-confirmed passing. Lint clean.

## 11. Remaining gaps

No automatic recursion into every accepted module (explicit non-goal; `submodel_module_id` is
opt-in only). No Agent 5 experimental-design logic — `calibration_request_provider` is a plain
injection point, not an implementation. `build_submodel`'s own network-truncation limitation
(disclosed in `agent2-antimony-builder/app/agent2/candidate_orchestration/round.py`) still
applies when recursing into a submodule. The real end-to-end subprocess chain for *this specific
new round-runner* is exercised by this harness's own production code path but is not covered by
a dedicated real-subprocess test in this increment (the existing real `sce00061` test and the
existing real module-calibration round trip each cover their own half already; a third, fully
real round-trip test combining both would be a reasonable follow-up, not added here to keep this
increment's own test run fast).
