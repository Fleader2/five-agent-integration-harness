# Hermetic Real-Workflow Testing

## 1. Problem

`tests/harness/test_real_sce00061_workflow.py` is this project's only
test that exercises the full, real, five-agent pipeline end to end (no
mocks, live subprocess invocations of all five agents). It originally
assumed the developer `agent1` database already contained a specific,
pre-curated yeast fatty-acid-biosynthesis dataset, keyed by a hardcoded
organism id. That assumption broke when the developer database was
emptied by an unrelated migration-verification step in the Agent 1
repository (see
`agent1-biochemical-curator/docs/32_sce00061_fixture_recovery.md` for
the full incident) — and, independent of that specific incident, it was
always a latent hermeticity gap: this test's own correctness depended
on persistent, mutable, out-of-band developer state that nothing in
this repository created, versioned, or could reset.

## 2. Design

The `real_workflow_report` fixture now:

1. Provisions a uniquely-named, disposable Postgres database by
   subprocess-invoking
   `agent1-biochemical-curator/scripts/sce00061_fixture.py provision`
   with Agent 1's own venv interpreter (the exact same
   `app.harness.subprocess_runner.run_stage_subprocess` helper
   `run_workflow` itself already uses for every real agent
   invocation — reused directly, not duplicated). That script creates
   the database, migrates it to head with Agent 1's own real Alembic
   chain, and seeds it with a real, live curation run (no mocks) — see
   its own module docstring.
2. Overrides `DATABASE_URL` in this test process's own environment for
   the duration of the real workflow run. This requires **no change** to
   `app.harness.pipeline`/`subprocess_runner` — both already forward the
   calling process's own `os.environ` to every stage's subprocess
   unchanged, so setting the override here is sufficient; Agent 1's
   subprocess picks it up automatically.
3. Runs one extra, real, live Agent 1 → Agent 2 subprocess pass (again,
   via `run_stage_subprocess` directly — the exact same runners
   `run_workflow` itself invokes) purely to discover one real,
   currently-valid, default-calibratable parameter id, and substitutes
   it into `tests/fixtures/sce00061_calibration_request.json`'s own
   `targets[0].target_id` before the real run. Needed because that
   fixture's own hardcoded `target_id` named a parameter from a past
   curation run — and every fresh curation run assigns fresh random
   entity ids, so a hardcoded id can never match a newly-provisioned
   database. Restricted to Agent 4's own `DEFAULT_CALIBRATABLE_PARAMETER_SOURCES`
   (`HEURISTIC_INITIALIZATION`/`PLACEHOLDER`/`DEFAULT`, `fixed is not True`) —
   picking an arbitrary parameter id intermittently selected a protected,
   evidence-backed parameter instead, which Agent 4 *correctly* refuses
   without explicit authorization (`INVALID_REQUEST`), a different,
   equally honest outcome from the one this fixture's own naming
   (`sce00061_calibration_request.json`'s `request_id`/
   `observation_set_id`: "no real data available") documents as its
   actual intent (`INSUFFICIENT_DATA` for a *valid* target with no real
   observations).
4. Runs the real `run_workflow` exactly as before.
5. In a `finally` block: restores the previous `DATABASE_URL` (or
   removes the override if there was none) and tears down the
   provisioned database via the same script's `teardown` subcommand —
   unconditionally, even if the run itself failed.

No change was made to `app.harness.pipeline`, `subprocess_runner.py`, or
any scoped-build code path (`runners/run_agent2.py`,
`scripts/run_workbench_request.py`) — this is entirely a test-file
change, consistent with "the harness orchestrates; it does not repair
scientific outputs."

## 3. What changed about the test's own expectations

`reaction`/`species` counts (38/53) have been exactly reproduced across
every independent real run observed while building this (3 separate
live curation runs). `kinetic_measurements` (72, not the historical 216)
is lower because two connectors (GotEnzymes2, the Open Enzyme Database)
were confirmed live-unreachable/degraded when
`sce00061_fixture.py` was written — see that script's own module
docstring and `agent1-biochemical-curator/docs/32_sce00061_fixture_recovery.md`
for the exact errors observed; this is disclosed, not silently patched.
Agent 2's own downstream parameter count is asserted as a floor (`>= 80`)
rather than an exact value: two otherwise-identical independent live
runs produced 87 and 91 respectively, a real, legitimate consequence of
Agent 2's own kinetic-evidence tie-breaking being sensitive to some
run-to-run variation in the live data Agent 1 supplies it, not a bug.

## 4. Cost

This test is now substantially more expensive than before: provisioning
a fresh database and running a real, live, multi-connector curation pass
takes on the order of 2-3 minutes, on top of the five real agent
subprocess invocations. It remains skipped (never failed) when no
Postgres server is reachable or the Agent 1 repository is unavailable,
exactly as before. This cost is the explicit, accepted price of removing
this test's dependency on mutable, unversioned developer state.
