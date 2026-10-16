# Workbench <-> Harness Hierarchical Recursion Contract

## 1. Goal

A second, genuinely separate Workbench-facing contract -- distinct from
`docs/07_workbench_harness_contract.md`'s own fixed five-agent `FULL_PIPELINE` workflow -- so the
Workbench can ask this harness to run one Automatic Hierarchical Recursive Modularization search
(`app.harness.hierarchical_recursion.run_hierarchical_recursive_modularization`) against a model
Agent 2 already assembled, and get back a result shaped for the Workbench to persist as a
first-class, queryable record (never a UI concern this harness itself addresses).

## 2. Contract types

`app/harness/workbench_contracts.py` (additive to the existing module -- `WorkbenchInvocationRequest`/
`WorkbenchRunResult`/`WorkbenchRunStatus`/`WorkbenchRunError`/`WorkbenchRunErrorCode` are all
reused unchanged where their meaning is generic enough):

* `WorkbenchHierarchicalInvocationRequest` -- `run_id`, `project_id`, `subproject_id`,
  `contract_version`, `criteria_weights`/`search_policy`/`calibration_selection_policy`/
  `flat_orchestration_policy`/`recursion_policy` (plain dicts, forwarded unread and unparsed --
  the identical "the Workbench need not understand an agent's own request shape" convention the
  `FULL_PIPELINE` contract already uses for Agent 4's/Agent 5's own request files);
  `functional_evaluation_selection_policy` (optional); `model_id`/`agent1_organism_id`/
  `input_artifact_references` (recognizes the identical `"stage1_synthetic_source"` key);
  `exclude_single_module_from_ranking`/`apply_resolution_correction`; `correlation_id`/`notes`/
  `submitted_at`.
* `WorkbenchHierarchyNodeSummary` -- one `HierarchyNodeRecord`, reshaped field-for-field into a
  plain, JSON-ready contract. Per-run policy/weight fields are deliberately *not* repeated per
  node (they are identical across every node of one run and already recorded once on the
  request).
* `WorkbenchHierarchicalRunResult` -- `status` (`WorkbenchRunStatus`, reused), `root_model_id`,
  `nodes` (the *full* set, never truncated -- the Workbench is expected to persist every one as
  its own first-class row, not just this summary blob), `total_nodes_created`/
  `total_functional_evaluations_used`/`total_calibration_runs_used`, `requires_user_review`,
  `pending_review_modules`, `recursion_policy_version`, `error`/`summary`/`warnings`/`replayed`.

`WORKBENCH_HIERARCHICAL_CONTRACT_VERSION` (currently `"workbench-hierarchical-v1"`) is this
contract's own version -- unrelated to `WORKBENCH_HARNESS_CONTRACT_VERSION` (the `FULL_PIPELINE`
contract) and unrelated to `app.harness.version.HIERARCHICAL_RECURSION_POLICY_VERSION` (the
underlying orchestration policy this contract wraps, never re-exposed or re-derived here). The
Workbench's own copy lives in `app/contracts/hierarchical_recursion.py` of that repository.

## 3. Canonical entrypoint

`scripts/run_workbench_hierarchical_request.py`:

```bash
.venv/bin/python3 scripts/run_workbench_hierarchical_request.py \
    --request /path/to/workbench_hierarchical_invocation_request.json \
    --output /path/to/workbench_hierarchical_run_result.json
```

Mirrors `run_workbench_request.py`'s own execution semantics exactly: parse (malformed ->
`MALFORMED_REQUEST`), idempotent replay keyed by `run_id`
(`artifacts/runs/<run_id>/workbench_hierarchical_result.json`), contract-version check
(mismatch -> `CONTRACT_VERSION_MISMATCH`), exactly-one-of `agent1_organism_id`/
`stage1_synthetic_source` (otherwise `INVALID_STAGE1_INPUT`; a missing/unreadable synthetic
source file is `MISSING_INPUT_ARTIFACT`), then the real
`run_hierarchical_recursive_modularization` call. A malformed *nested* policy dict (e.g.
`recursion_policy` missing one of its own required keys) is caught and reported as
`MALFORMED_REQUEST` rather than an uncaught traceback. The full, unabridged
`HierarchicalRecursionResult` (every node) is written in full to
`hierarchical_recursion_result.json` for complete traceability, exactly mirroring
`workflow_report.json`'s own "summary vs. full report" split.

## 4. No calibration dataset provider

Unlike the `FULL_PIPELINE` contract (which forwards real Agent 4/Agent 5 request files), this
contract has no dataset-provider mechanism at all: the entrypoint always uses a calibration
request provider that returns no dataset, so every `CALIBRATE` decision resolves as
`NO_DATASET_AVAILABLE` -- a disclosed scope limit (deciding what counts as a usable calibration
dataset for an arbitrary candidate module is Agent 5's own future job), never a silent
fabrication. The entrypoint always discloses this via a standing warning line.

## 5. Agent 1 input

Exactly one of `agent1_organism_id` (invokes Agent 1 as a real subprocess, identical to
`app.harness.pipeline.run_workflow`'s own Stage 1) or
`input_artifact_references["stage1_synthetic_source"]` (test/dev-only, a hand-authored Agent 1
view JSON) must be set -- the identical requirement and the identical disclosed test/dev-only
status the `FULL_PIPELINE` contract already documents.

## 6. No scientific logic added

Nothing in this contract or its entrypoint inspects, transforms, or re-derives any node's own
acceptance decision, score, or stopping reason -- every field is read verbatim from the
already-existing `HierarchicalRecursionResult`/`HierarchyNodeRecord` and reshaped into this
contract's own plain dict/dataclass shape. All of the actual decision logic lives in
`app.harness.hierarchical_recursion` (unchanged by this increment) and, one layer below that,
Agent 2's own `materialize_submodel`/`build_submodel`/candidate search.

## 7. Tests

`tests/harness/test_workbench_hierarchical_contracts.py` (13 tests, mirrors
`test_workbench_contracts.py`'s own module-scoped-real-subprocess convention): contract
round-trip serialization; malformed-request/malformed-nested-policy/contract-mismatch/
invalid-stage1-input/missing-artifact pre-flight rejections (fast, no subprocess); one real,
live end-to-end subprocess invocation of the canonical entrypoint against the repository's own
synthetic fixture, confirming a real two-node hierarchy, nonzero `total_nodes_created`, the
disclosed `NO_DATASET_AVAILABLE` warning, and idempotent replay. Full harness suite: 138 passed
(125 pre-existing + 13 new); lint clean repository-wide.

## 8. Resume contract (human-review/resume increment)

A second, additive entrypoint, `scripts/run_workbench_hierarchical_resume_request.py`, wraps
the harness's own (otherwise unchanged) `app.harness.hierarchical_recursion
.resume_hierarchical_recursive_modularization`:

* `WorkbenchHierarchicalRunResult` gains one new, optional field: `checkpoint: dict | None` --
  the harness's own `serialize_checkpoint(...)` dict, populated verbatim whenever
  `requires_user_review` is `True`. The Workbench stores this exactly as received and never
  reinterprets its internal shape.
* `WORKBENCH_HIERARCHICAL_RESUME_CONTRACT_VERSION` (`"workbench-hierarchical-resume-v1"`) --
  deliberately its own version, separate from `WORKBENCH_HIERARCHICAL_CONTRACT_VERSION` (the
  *initial*-invocation contract).
* `WorkbenchHierarchicalResumeRequest` -- `run_id`, `contract_version`, `checkpoint` (the
  Workbench's own stored copy of a prior result's `checkpoint`, passed back unchanged),
  `decisions` (a `{pending_id: "APPROVE"|"REJECT"}` mapping), `correlation_id`/`notes`/
  `submitted_at`. The result reuses the identical `WorkbenchHierarchicalRunResult` shape.
* `WorkbenchRunErrorCode.CHECKPOINT_REJECTED` -- the new error code for a
  `HierarchicalRecursionCheckpointError` (malformed, version-mismatched/stale, or
  decision-incomplete checkpoint), reported cleanly, never an uncaught exception.

Execution semantics mirror the initial-invocation entrypoint's own: idempotent replay keyed by
`run_id` (each resume attempt is expected to carry its own, fresh `run_id`, under
`workbench_hierarchical_resume_result.json`), a calibration dataset provider that always
returns no dataset, and the full, unabridged `HierarchicalRecursionResult` written for
traceability alongside the reshaped Workbench result. No resume/checkpoint semantics are
duplicated here -- every decision is still made entirely inside
`app.harness.hierarchical_recursion`.

`tests/harness/test_workbench_hierarchical_resume_contract.py` (9 tests): resume-request/
result-with-checkpoint round-trip serialization; contract-mismatch/malformed-checkpoint/
malformed-request pre-flight rejections (fast, no subprocess); one real, live end-to-end
resume invocation chained off a real paused initial run (module-scoped fixtures), confirming
the resumed result succeeds, the root node is carried through unchanged (never re-searched),
and idempotent replay. Full harness suite: 164 passed; lint clean repository-wide.
