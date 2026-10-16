# Automatic Functional-Evaluation Selection and Caching in Recursive Candidate Search

## 1. Goal

Mirror the existing calibration-routing loop in `app.harness.recursive_candidate_search` with a
second, genuinely separate loop: whatever Agent 2's own new
`FunctionalEvaluationSelectionPolicy` gate selects each round is routed through Agent 3
(`app.harness.module_functional_evaluation`, unchanged), with its own cache and its own budget,
independent of calibration's. See the Agent 2 repository's own
`docs/39_automatic_functional_evaluation_selection_and_caching.md` for the Agent 2-side gate
design this loop drives.

## 2. Cache identity

`functional_evaluation_cache_key_for(content_key_pairs, boundary_species_ids,
perturbation_targets)` (`cache.py`) mirrors `cache_key_for`'s own structure, naming exactly what
task instructions §3 requires: module content, boundary species (the request's own
`boundary_species_ids`, standing in for "boundary treatment" since a functional-evaluation
request names boundary *species*, not declared `ModulePort` pairs), the full perturbation-target
battery (`target_kind`/`target_id`/`fraction`/`is_internal`, sorted), and the relevant policy
versions -- `FUNCTIONAL_EVALUATION_WORKFLOW_POLICY_VERSION`, `AGENT3_CONTRACT_VERSION`,
`RECURSIVE_CANDIDATE_SEARCH_POLICY_VERSION`. Never `AGENT4_CONTRACT_VERSION`: no Agent 4 call is
ever involved in a functional-evaluation round trip, so baking that version in would invalidate
the cache on an unrelated change.

`FileCalibrationEvidenceCache` itself needed no new class: `get`/`put` were already generic
(`cache_key -> JSON dict`), so the orchestration loop simply instantiates a second one pointed
at `stage_dir / "functional_evaluation_cache"` (a separate directory, never shared with
calibration's own cache, even though the class is identical).

Confirmed: an identical module/boundary/battery reuses cached evidence across rounds and across
separate orchestration invocations (same `stage_dir`); a changed perturbation-target battery or
changed boundary species produces a genuinely different cache key and is never incorrectly
reused.

## 3. Agent 3 invocation / budget behavior

Unlike calibration, a functional-evaluation request needs no external dataset provider at all
-- `run_module_functional_evaluation_workflow(request, *, stage_dir, timeout_seconds)` is fully
self-contained (Agent 2 already built the whole-network handoff and perturbation battery), so
the orchestration loop calls it directly for every `EVALUATE` decision without an analog of
`calibration_request_provider`/`NO_DATASET_AVAILABLE`. `total_functional_evaluations_used` is
incremented only for a genuinely new, successful Agent 3 round trip -- never for a cache hit or
a locally-resolved outcome, mirroring `total_calibration_runs_used` exactly.
`ModuleFunctionalEvaluationWorkflowError` (an Agent 3 subprocess crash/timeout) is never cached,
never counted toward the budget, and is retried on the very next attempt that reaches it.

`functional_evaluation_selection_policy` is an entirely optional parameter to
`run_recursive_candidate_search` (default `None`) -- when omitted, the orchestration never even
inspects `round_summary`'s own functional-evaluation fields (an explicit guard, not just reliance
on Agent 2 never producing any), so a caller upgrading to this increment's new code sees zero
behavior change until it opts in.

## 4. Functional-evidence feedback

Each round's own accumulated functional evidence (`accumulated_functional_evidence`, keyed by
content key exactly like calibration's own `accumulated_evidence`) is serialized into a
`--functional-evaluation-evidence` file and passed to the next round's own
`invoke_agent2_candidate_search_round` call, which Agent 2's own
`run_agent2_candidate_search_round.py` runner parses back into the
`Mapping[ModuleContentKey, ModuleFunctionalEvaluationResult]` shape
`run_candidate_search_round` already threads through unchanged (prior increment).

## 5. Interaction with calibration routing

Both loops read from and write to entirely separate state (`accumulated_evidence` vs.
`accumulated_functional_evidence`; `cache` vs. `functional_cache`;
`total_calibration_runs_used` vs. `total_functional_evaluations_used`); confirmed directly
(`test_functional_and_calibration_routing_are_independent`): zero `CALIBRATE` decisions this
round never prevents a real `EVALUATE`-driven Agent 3 round trip from running normally.

## 6. Stopping/human-review integration

A new `StoppingReason.FUNCTIONAL_EVALUATION_BUDGET_EXHAUSTED` is checked independently of
`CALIBRATION_BUDGET_EXHAUSTED`, in the same per-round stopping-condition sequence as every other
rule (`require_human_review` first, then candidate/calibration/functional budgets, then
search-exhausted/repeated-candidate-set/stable-boundary/no-improvement) -- the orchestration
still reports exactly one, explicit stopping reason, and `RecursiveCandidateSearchResult` gains
`total_functional_evaluations_used` alongside the existing `total_calibration_runs_used`.
`RoundRecord` gains `functional_evaluation_runs` (a `FunctionalEvaluationRunRecord` per routed
`EVALUATE` decision, recording outcome/cache_key/Agent 3 report id/reason) -- full provenance,
mirroring `calibration_runs` exactly.

## 7. Tests / lint

`tests/harness/test_functional_evaluation_orchestration.py` (13 tests): cache-key determinism
and sensitivity to boundary species/perturbation battery; omitting the policy never invokes the
runner; cached evidence reused across rounds; changed battery/boundary invalidates the cache;
an infrastructure failure is never cached and is retried; locally-resolved evidence requires no
round trip; the functional-evaluation budget stopping reason; functional and calibration
routing are independent; deterministic repeated execution (separate `stage_dir`s); the policy
is threaded to every round call. A real, live subprocess smoke test of the extended Agent 2
runner script (`run_agent2_candidate_search_round.py`'s new
`--functional-evaluation-selection-policy` flag), run directly against a real
`run_agent2_pipeline`-built model, confirmed the new CLI wiring produces a correctly-shaped,
real `INSUFFICIENT_TARGETS` local resolution end to end (the synthetic fixture's own 3-reaction
network is too small to produce a real Agent 3 round trip, but exercises the identical code
path a larger network would). Full harness suite (non-DB): 114 passed (101 pre-existing + 13
new); the real, live `sce00061` five-agent workflow test is unaffected (untouched by this
increment). Lint clean repository-wide.

## 8. Remaining gaps

Identical to the Agent 2 repository's own disclosed list: no automatic recursive descent; no
dataset-provider analog for functional evaluation (none needed, by design); the
"could-plausibly-change-ordering" gate is a conservative, never-over-selecting heuristic.
