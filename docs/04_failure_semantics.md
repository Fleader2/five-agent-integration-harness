# Failure Semantics

## The one rule that governs every status decision

> Never converts `INSUFFICIENT_DATA` or similar honest outcomes into success — and never
> converts a genuine failure into a false success either.

## Status vocabulary and precedence

`app.harness.types.WorkflowStatus`, checked in this exact order by
`app.harness.pipeline._determine_overall_status`:

1. **`BLOCKED`** — a stage could not even be attempted (that agent's repository directory or
   venv interpreter does not exist, or, for Agent 1, the live database is unreachable). Nothing
   about that agent's own code ran at all.
2. **`CONTRACT_MISMATCH`** — a producing stage's own declared contract version did not match
   what the consuming stage's own code expects. Detected *before* the consuming stage's
   subprocess is ever started (see `docs/02_contract_version_matrix.md`).
3. **`AGENT_STAGE_FAILED`** — a stage's own subprocess ran but exited with a genuine failure (an
   uncaught exception in that agent's own code — confirmed, in this repository's own tests, by
   deliberately feeding Agent 3 a handoff missing a required field and observing a clean,
   non-zero exit with the real `HandoffContractError` traceback captured, never a harness-level
   crash).
4. **`INVALID_ARTIFACT`** — a stage's own output file could not be parsed as JSON, or a
   post-hoc invariant check (see `docs/01_orchestration_architecture.md` for what these check)
   failed after all five stages otherwise appeared to succeed.
5. **`SUCCESS_WITH_EXPECTED_DATA_GAPS`** — every stage ran to completion, and at least one
   stage's own status is itself an honest, designed-for data-insufficiency outcome (Agent 4's
   own `CalibrationStatus.INSUFFICIENT_DATA`, Agent 5's own
   `ValidationStatus.INSUFFICIENT_VALIDATION_DATA`). **This is the status the real `sce00061`
   fixture is expected to produce, and does** — see `docs/06_version1_success_criteria.md` for
   why this counts as complete, successful integration-test behavior, never a failure.
6. **`SUCCESS`** — every stage ran to completion with no data-insufficiency outcome anywhere in
   the chain (the synthetic ground-truth fixture's own expected result).

## What "stops cleanly" means in code

Every early-exit path in `app.harness.pipeline.run_workflow` returns a fully-formed
`FiveAgentWorkflowReport` via the shared `_finish` helper — there is no code path where a
mid-workflow problem raises an uncaught Python exception out of `run_workflow` itself. A caller
(a test, `scripts/run_fixture_a.py`/`run_fixture_b.py`) always receives a complete, inspectable
report object, whatever went wrong. The only exceptions `run_workflow` can itself raise are
genuine harness-internal bugs (e.g. a malformed `WorkflowRunRequest`), never a downstream
agent's own reported outcome.

## What never happens

- A stage's own subprocess timing out or crashing is never retried silently, never masked by a
  default/fallback value, and never reported as anything other than `AGENT_STAGE_FAILED`/
  `BLOCKED`.
- A downstream stage is never invoked once an upstream contract-version check has already
  failed — there is no "try anyway and see" path.
- `SUCCESS_WITH_EXPECTED_DATA_GAPS` is never collapsed into plain `SUCCESS` in the stored
  report — a reader must always be able to tell "everything actually worked end to end, with
  real data throughout" from "everything worked, but there wasn't enough real data to
  calibrate/validate against" by reading `overall_status` alone, never by having to inspect
  every stage's own findings first.
