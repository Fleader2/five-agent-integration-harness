# Orchestration Architecture

## Central rule

> The integration harness orchestrates existing agents; it does not duplicate agent logic or
> silently repair their outputs.

## Why every stage is a subprocess, never an import

Every agent repository in this project family (`agent1-biochemical-curator` through
`agent5-validation-experimental-design`) uses the identical top-level package name `app`
(`app.agent1`, `app.agent2`, ... each rooted at its own repository, with its own venv and
pinned dependency versions). Importing two of them in the same Python process is not just
against this project's own established decoupling convention — it is not even structurally
possible without colliding `sys.modules` entries.

The harness therefore never imports a sibling agent's Python package. Instead, each stage is a
small, self-contained **runner script** (`app/harness/runners/run_agentN.py`), executed as a
separate OS subprocess using that agent's own `.venv/bin/python3` interpreter, with
`PYTHONPATH` and the process working directory both set to that agent's own repository root.
This is a structural necessity, not a stylistic choice, and it happens to be exactly what "the
harness orchestrates; it does not duplicate agent logic" means in practice: a runner script
calls that agent's own already-committed, already-tested entrypoint function(s) and writes back
whatever that function returns — it contains no modeling, calibration, or diagnostic logic of
its own.

## What each runner script does

| Script | Agent | Calls | Never does |
|---|---|---|---|
| `run_agent1.py` | Agent 1 | `get_agent1_knowledge_package` → `get_agent1_curated_knowledge_view` against the live, already-curated Postgres database | Write to the database, make a network/LLM call, invent a field |
| `run_agent3.py` | Agent 3 | `parse_agent2_handoff` → `run_agent3_pipeline` | Alter the model, retry with different tolerances |
| `run_agent4.py` | Agent 4 | `parse_agent4_handoff` → `run_agent4_pipeline` | Fit anything the request does not explicitly authorize |
| `run_agent5.py` | Agent 5 | `parse_agent5_handoff` → `run_agent5_pipeline` | Recalibrate, or feed validation data back into fitting |

Each script's own inline `_to_jsonable` serializer is a small, generic, duplicated (not shared)
helper that converts that agent's own dataclasses/enums (and, for Agent 1 only, raw SQLAlchemy
ORM rows — see that script's own comment) into a plain JSON-serializable structure. This
duplication is deliberate: sharing a `app.harness` serialization helper with a runner script
would require putting the harness's own package on that subprocess's `PYTHONPATH` alongside the
target agent's — which, since both are named `app`, would silently make one of the two
unresolvable. A ~15-line generic serializer duplicated four times is harness plumbing, not
agent logic, and is the correct trade-off here.

## Agent 2's own canonical entrypoint: a genuine live invocation, for both fixtures

**Five-Agent Workflow V1 Hardening increment.** Agent 2's own real assembly pipeline was, before
this increment, a chain of at least eleven discrete stage functions
(`translate_agent1_view_to_agent2` → `assemble_full_network` → reaction-context resolution →
`characterize_full_network` → `assign_kinetic_laws` → `resolve_enzyme_concentrations` →
`build_enzyme_state_dynamics` → a two-pass `declare_parameters`/`assess_boundaries`/
`decompose_network` wiring → `assemble_model_specification` → `generate_antimony`) with no
single, already-tested, official entrypoint chaining them correctly end to end — so the
pre-hardening harness **consumed** a pre-existing, already-committed Agent 2 output artifact for
Stage 2 rather than risk hand-chaining that sequence incorrectly.

Agent 2's own `agent2-antimony-builder` repository now commits exactly that entrypoint:
`app.agent2.pipeline.run_agent2_pipeline` (CLI: `scripts/run_agent2_pipeline.py`; see that
repository's own `docs/19_canonical_orchestration_entrypoint.md` for the full stage-by-stage
evidence trail). `app/harness/runners/run_agent2.py` is now a thin wrapper around that one real
function. Stage 2 is therefore a genuine, live subprocess invocation of Agent 2's own real
pipeline **for both fixtures**, fed directly from whatever Stage 1 produced — never a copy of a
pre-existing artifact, and never a hand-authored `agent2_model` dict. This resolves the
pre-hardening "consume, don't invoke" scope limitation entirely.

## The contract-version re-stamping adapters — removed

A related, smaller pre-hardening finding: Agent 3, Agent 4, and Agent 5 each independently
declared their own name for what was already, structurally, the identical `agent2_model`
artifact shape (`"agent2-to-agent3-v1"`, `"agent2-agent3-to-agent4-v1"`,
`"agent2-agent4-to-agent5-v1"` respectively). **Five-Agent Workflow V1 Hardening increment:**
Agent 2's own `app.agent2.pipeline` now emits exactly one canonical contract version,
`AGENT2_DOWNSTREAM_CONTRACT_VERSION = "agent2-downstream-v1"`, and Agents 3, 4, and 5 have all
been migrated to expect that identical string. `app.harness.adapters` no longer re-stamps
anything — `_restamp_contract_version` has been removed entirely, and `build_agent4_handoff`/
`build_agent5_handoff` now wrap `agent2_model` exactly as Stage 2 produced it, byte-for-byte. See
`docs/02_contract_version_matrix.md` for the resolved matrix, and
`app.harness.invariants.check_no_contract_version_restamping` for the new end-to-end check that
this never silently regresses.

## Fixture B's own, separately disclosed scope decision

Agent 1's own runtime is still not invoked for the fully synthetic fixture (no real literature
exists to curate for a hand-authored ground-truth system): a static, hand-authored Agent 1 view
JSON (`tests/fixtures/synthetic_agent1_view.json`) is supplied directly as Stage 1's own output.
Agent 2, however, is now genuinely, live invoked against it through the same canonical entrypoint
as the real-yeast fixture — never a hand-authored `agent2_model` artifact.

The one remaining disclosed exception: no increment of Agent 2's own pipeline yet populates
species initial concentrations or compartment initial volume for *any* input (confirmed a
genuine, pre-existing, upstream scope gap — also present on the real `sce00061` model, which is
exactly why Fixture A's own Agent 3 stage reports `STEADY_STATE_NOT_FOUND`). Fixture B exists to
exercise calibration/validation/experimental-design logic against a *known* ground truth, which
requires the model to actually simulate from the intended starting state, so
`app.harness.synthetic_fixture.patch_synthetic_ground_truth_initial_conditions` applies one
minimal, clearly-disclosed post-processing step to Agent 2's own real output afterward — setting
only `species[].initial_concentration`/`initialization_source`,
`compartments[].initial_volume`/`volume_unit`/`constant`, and the matching Antimony initial-value
assignments. Every other field (species/reactions/kinetic_laws/parameters/model structure) is
Agent 2's own real, completely unmodified pipeline output. Agent 3, Agent 4, and Agent 5 are then
genuinely, live invoked against the patched artifact — exercising real calibration, real
validation, and real experimental-design ranking against a model whose true parameters are known
by construction.

## Every stage's own artifact is written before the next stage runs

`app.harness.pipeline.run_workflow` writes `stageN_output.json` (and, for Agent 4/5,
`stageN_input.json`) to the run's own stage directory immediately after that stage completes,
before the next stage is ever invoked — see `docs/03_artifact_directory_layout.md`. A contract-
version check runs against the just-written artifact before the next stage's subprocess is
started; a mismatch stops the run immediately (see `docs/04_failure_semantics.md`).
