# Running the Canonical Fixtures

## Prerequisites

Each of the five sibling agent repositories must already have its own `.venv` set up (per that
repository's own README) at the standard sibling-directory location
(`app.harness.repo_paths` assumes `../agent{1,2,3,4,5}-*` relative to this repository). Fixture
A additionally requires Agent 1's live Postgres database to be reachable (the same
`postgresql://agent1:agent1@localhost:5432/agent1` every real fixture in this project's history
has used) and migrated to its latest revision (`cd agent1-biochemical-curator && .venv/bin/
alembic upgrade head`).

## Fixture A — the real `sce00061` workflow

```bash
cd agent-integration-harness
.venv/bin/python3 scripts/run_fixture_a.py
```

Invokes Agent 1 live against the real yeast fatty-acid-biosynthesis curation data, then
genuinely, live invokes Agent 2's own canonical orchestration entrypoint
(`app.agent2.pipeline.run_agent2_pipeline`) directly against that fresh output — never a copy of
a pre-existing artifact (see `docs/01_orchestration_architecture.md`) — and genuinely, live
invokes Agent 3, Agent 4, and Agent 5. No real calibration or validation observation data exists
for this model, so Agent 4 and Agent 5 are expected — honestly, not as a bug — to report
`INSUFFICIENT_DATA`/`INSUFFICIENT_VALIDATION_DATA`. The overall result is
`SUCCESS_WITH_EXPECTED_DATA_GAPS`, which **is** this fixture's own definition of success (see
`docs/06_version1_success_criteria.md`).

Do not supply real observation data to this fixture's own requests merely to obtain a
`SUCCESS` result instead — that would be exactly the "invent a biological observation" failure
mode the whole five-agent system, and this harness, exist to prevent.

## Fixture B — the fully synthetic ground-truth workflow

```bash
cd agent-integration-harness
.venv/bin/python3 scripts/run_fixture_b.py
```

Agent 1's own runtime is still not invoked (disclosed, deliberate scope decision — no real
literature exists for a hand-authored system): `tests/fixtures/synthetic_agent1_view.json`, a
static, hand-authored Agent 1 view describing a three-reaction chain `S1 -> S2 -> S3 -> S4` with
true rate constants `0.5`, `0.2`, `0.1`, is supplied directly as Stage 1's own output. Agent 2,
however, is genuinely, live invoked against it through the same canonical entrypoint as Fixture
A — never a hand-authored `agent2_model` artifact. The one disclosed exception:
`app.harness.synthetic_fixture.patch_synthetic_ground_truth_initial_conditions` patches species
initial concentrations and compartment initial volume onto Agent 2's own real output afterward
(a pre-existing, documented scope gap in Agent 2's own pipeline — see `docs/
01_orchestration_architecture.md`); every other field is Agent 2's own real, unmodified output.
Agent 3, Agent 4, and Agent 5 are then genuinely, live invoked against the patched artifact. The
well-constrained rate constant (reaction 1, true value `0.5`) and the second (reaction 2, true
value `0.2`) are recovered from the supplied training data (`S1`/`S2` time series); the third
(reaction 3, true value `0.1`) is **deliberately** left unconstrained (the training and
validation sets never observe `S3`/`S4`), to exercise Agent 4's own identifiability diagnostics
and Agent 5's own experimental-design ranking against a target genuinely worth recommending a
new measurement for.

The script prints true-vs-recovered parameters, the calibration objective before/after, and the
top-ranked candidate experiments — see `docs/06_version1_success_criteria.md` for what counts
as a successful run of this fixture.

## Re-running only part of a workflow

`app.harness.pipeline.run_workflow` is a single function; there is no partial-resume feature in
Version 1. To inspect or re-run a single stage in isolation, invoke that stage's own runner
script directly (see the table in `docs/01_orchestration_architecture.md`) against an existing
`stageN_output.json` from a prior run's own `artifacts/runs/<run_id>/` directory.
