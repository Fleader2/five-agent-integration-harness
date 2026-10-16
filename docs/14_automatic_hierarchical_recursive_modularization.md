# Automatic Hierarchical Recursive Modularization

## 1. Goal

Allow an accepted modularization to be recursively refined into nested submodules, using the
existing canonical submodel materialization (Agent 2), structural search (Agent 2), Agent 3
functional evaluation, and Agent 4 calibration evidence -- a second recursion *dimension*
(depth into submodules) layered entirely on top of the existing, unchanged flat recursive
search (one call per hierarchy node), never duplicating Agent 2's own search/evaluation logic.

## 2. Hierarchy API

```python
run_hierarchical_recursive_modularization(
    *, agent1_view_path, criteria_weights, search_policy, calibration_selection_policy,
    flat_orchestration_policy, recursion_policy, calibration_request_provider, stage_dir,
    correlation_id, run_id_prefix,
    functional_evaluation_selection_policy=None, seed_modularization_id=None,
    exclude_single_module_from_ranking=True, apply_resolution_correction=False,
    build_request_path=None, recursive_search_runner=run_recursive_candidate_search,
    cache=None, functional_cache=None, timeout_seconds=300.0,
) -> HierarchicalRecursionResult
```

One call per hierarchy *node*: the root (the whole canonical model) plus, recursively, one call
per module of each accepted modularization that is eligible for subdivision. Every node calls
`app.harness.recursive_candidate_search.run_recursive_candidate_search` exactly as it already
exists (injectable via `recursive_search_runner` for testing) -- this package performs no
structural search, scoring, or evidence routing of its own.

## 3. How a child node reaches its own submodel

Each node's own flat recursive search already returns, in its final round's own
`round_summary`, every module's content-key pairs for every retained candidate (via
`calibration_decisions`, which always carries exactly one decision per module of every retained
candidate, regardless of outcome -- `select_candidates_for_calibration`'s own, unconditional
guarantee). To descend into one eligible module, this driver forwards that *exact,
already-computed* structure back to Agent 2 as a new `attach_modularization` payload --
`run_agent2_candidate_search_round.py` (the Harness-owned runner script executed inside Agent
2's own venv) attaches it to the freshly-rebuilt model (via `dataclasses.replace`, before
`--seed-modularization-id`/`--submodel-module-id` resolve) and then calls Agent 2's own existing
`build_submodel`/`materialize_submodel` exactly as it already does for the model's own original
seed modularization. Nothing new was added to Agent 2's own Python package -- the runner script
lives in this repository and already imports Agent 2's types/functions directly.

## 4. Descent policy

`HierarchicalRecursionPolicy`: `max_depth`, `min_reactions_per_module`,
`max_total_hierarchy_nodes`, `max_total_functional_evaluation_budget`,
`max_total_calibration_budget`, `min_improvement_to_accept_child` (a `Decimal`-parseable
string, mirroring `OrchestrationPolicy.improvement_epsilon`'s own convention),
`require_human_review`, `policy_version`. A module is eligible for subdivision only when its
own retained-candidate content key names at least `min_reactions_per_module` `REACTION`
entries -- counted directly from the already-harvested content-key pairs, never re-derived
structurally. No module is ever subdivided blindly: ineligible modules are simply never
descended into, and every node's own descent decision is independently recorded.

## 5. Child acceptance rule

A child decomposition is accepted only when its own best retained candidate's `overall_score`
exceeds the degenerate ("leave the parent module intact") baseline's own score -- under the
*identical* `criteria_weights`, so `TOPOLOGICAL_SEPARATION`/resolution correction/
`DYNAMIC_ISOLATION`/`SENSITIVITY_COHERENCE`/`CALIBRATION_INDEPENDENCE` all contribute exactly as
they already do -- by at least `min_improvement_to_accept_child`. The degenerate baseline is
the *same* single-module evaluation `exclude_single_module_from_ranking`'s own existing,
one-module-reference-only behavior already produces (never a new scoring path); every child
level forces `exclude_single_module_from_ranking=True` regardless of the caller's own root-level
choice, since the acceptance rule has nothing to compare against otherwise -- a real bug caught
by a live subprocess smoke test during development (the root's own `False` was being forwarded
unchanged to every child, silently disabling the baseline), fixed and regression-tested
(`test_every_child_level_forces_exclude_single_module_from_ranking`). The root node has no
parent to leave intact and is accepted whenever a genuine, non-degenerate candidate exists at
all.

## 6. Hierarchy representation and lineage

`HierarchyNodeRecord`: `node_id`, `depth`, `root_model_id` (shared by every node),
`parent_modularization_id`/`parent_module_id` (`None` only for the root), `child_submodel_id`
(the materialized submodel's own content-addressed `model_id`), `child_modularization_id`/
`child_module_ids` (the accepted candidate's own ids), `accepted`, `reason`, `baseline_score`/
`child_score`, `branch_stopping_reason`, every policy/weight in effect, and the node's own flat
search's `stopping_reason`/round count/policy version. The hierarchy is deterministically
reconstructable: `parent_modularization_id` of any non-root node always equals its own parent's
`child_modularization_id`, and `root_model_id` is identical across every node.

## 7. Global budget behavior

`max_total_hierarchy_nodes`/`max_total_functional_evaluation_budget`/
`max_total_calibration_budget` are tracked in one shared, mutable state dict across the entire
recursive descent -- never reset per branch or per child. Before calling the flat search for
any node beyond the root, this driver checks the *global* remaining functional/calibration
budget and skips the node entirely (recording `FUNCTIONAL_EVALUATION_BUDGET_EXHAUSTED`/
`CALIBRATION_BUDGET_EXHAUSTED`) if either is already spent -- never attempting a call that
could not possibly do anything useful. Each node's own flat search is handed only the
*remaining* budget as its own local ceiling, and the real usage it reports back
(`total_functional_evaluations_used`/`total_calibration_runs_used`, incremented only for a
genuinely new round trip, never a cache hit) is subtracted from the global pool afterward.

## 8. Cache reuse

A single pair of `FileCalibrationEvidenceCache` instances (one for calibration, one for
functional evaluation) is created once and passed, by shared reference, to *every* node's own
flat-search call -- confirmed directly
(`test_shared_cache_instances_are_passed_to_every_level`). Cache identity is already keyed by
module content alone (unchanged from the flat-search increment), so a module whose content
happens to recur at a different hierarchy position reuses its evidence automatically; a cache
hit never consumes either global budget (the flat search's own, unchanged discipline).

## 9. Branch stopping rules

`HierarchyBranchStoppingReason`: `MAX_DEPTH`, `MODULE_TOO_SMALL` (checked before a node is even
attempted -- an ineligible module gets its own cheap, disclosed record, but is never actually
materialized or searched, and never consumes a hierarchy-node budget slot), `NO_ELIGIBLE_MODULES`
(every module of an accepted candidate was too small, or none exist at all),
`NO_VALID_CHILD_DECOMPOSITION` (the flat search never retained a genuine candidate),
`INSUFFICIENT_IMPROVEMENT`, `STABLE_BOUNDARIES` (the child's own flat search converged --
`STABLE_BOUNDARY_CONVERGENCE`/`REPEATED_CANDIDATE_SET` -- so the accepted decomposition stands,
but its own children are never explored this call), `MAX_HIERARCHY_NODES_EXHAUSTED`,
`FUNCTIONAL_EVALUATION_BUDGET_EXHAUSTED`, `CALIBRATION_BUDGET_EXHAUSTED`,
`INSUFFICIENT_EVIDENCE` (no degenerate baseline to compare against at all), `HUMAN_REVIEW_GATE`.
Every node that stops descending further records exactly one of these on its own
`HierarchyNodeRecord`; an accepted node that *does* keep descending records `None`.

## 10. Human review

`recursion_policy.require_human_review=True` makes every *accepted* node stop before
descending into any of its own eligible modules: `HierarchicalRecursionResult
.requires_user_review=True`, and `pending_review_modules` lists exactly those eligible
modules (`parent_node_id`, `depth`, `parent_modularization_id`, `module_id`, `reaction_count`)
-- "proposed next modules for subdivision," never yet searched. The current hierarchy-so-far is
simply `result.nodes`. This increment does not implement resuming a paused hierarchy from a
saved point across separate calls (a disclosed scope limit, not an oversight -- out of scope
alongside UI, per task instructions).

## 11. Example multi-level hierarchy

A real, live subprocess run against the repository's own synthetic 3-reaction fixture:
depth 0 accepts the whole network as `candidate::gen0::0001`; depth 1 attempts to subdivide the
whole-network module further and is recorded as `NO_VALID_CHILD_DECOMPOSITION` (too small a
network for a second meaningful split under 1 search iteration) -- confirming the real,
end-to-end materialize-submodel-then-search-then-accept-or-reject chain runs correctly through
real Agent 2 subprocess calls, not just injected fakes.

## 12. Tests / lint

`tests/harness/test_hierarchical_recursion.py` (11 tests, fake-injected `recursive_search_runner`,
mirroring `test_recursive_candidate_search.py`'s own convention one level up): successful
two-level hierarchy with selective descent into only eligible modules; depth limit; global
calibration-budget enforcement across levels (a child is skipped entirely, never even calling
the runner, once the root exhausts the shared pool); shared cache instances passed to every
level; poor child decomposition rejected for insufficient improvement; human-review pause
(descends zero levels, returns the correct pending-review list); deterministic repeated
execution; complete, reconstructable parent/child lineage; GENERATED/IMPORTED-origin-agnostic
behavior (the driver only ever reads generic dict shapes); never mutates caller-supplied
policy/weight dicts; and a regression test for the real `exclude_single_module_from_ranking`
bug caught by the live subprocess smoke test above. Full harness suite (non-DB): 125 passed
(114 pre-existing + 11 new); real `sce00061` five-agent workflow unaffected (untouched by this
increment). Agent 2 (1313 passed, zero files touched this increment), Agent 3 (37 passed),
Agent 4 (64 passed), and Workbench (88 passed) all pass unchanged. Lint clean repository-wide.

## 13. Remaining gaps

- No resumable human-review state across separate calls (disclosed above).
- A pre-existing, *not newly introduced* risk, found while fixing this increment's own
  filename-length bug: `app.agent2.candidate_orchestration`'s own calibration/functional
  request-building embeds the real (potentially very long, content-addressed) `module_id`
  directly into each request's own `run_id`, which `app.harness.module_calibration`/
  `.module_functional_evaluation` then use to build a real file path. A sufficiently large
  module could, in principle, hit the identical `OSError: File name too long` this increment's
  own `run_id`/`node_id` construction was caught doing and fixed
  (`_short_module_tag`) -- but fixing that pre-existing path is Agent 2/the flat-search
  increment's own repository boundary, out of scope here, and disclosed rather than silently
  patched around.
- No automatic selection of *which* root-level accepted modularization to use beyond "the
  top-ranked retained candidate of the final round" -- a deterministic, simple, but singular
  choice; task instructions do not ask for alternative selection strategies.
