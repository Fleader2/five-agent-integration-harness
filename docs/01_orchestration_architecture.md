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

## The one deliberate "consume an artifact" boundary: Agent 2

The task's own instructions explicitly allow a stage to be satisfied by "invokes **or
consumes** each agent's documented entrypoint/artifact." Agent 2's own real assembly pipeline
is not a single function — it is a chain of at least eleven discrete stage functions
(`translate_agent1_view_to_agent2` → `assemble_full_network` → optional enzyme-concentration/
enzyme-state-dynamics resolution → `characterize_full_network` → `assign_kinetic_laws` →
`declare_parameters` → `assess_boundaries` → `decompose_network` →
`assemble_model_specification` → `generate_antimony`), confirmed this session to have **no
existing, already-tested, single entrypoint or script** that chains them correctly end to end,
and at least one intermediate step (reaction-context resolution) whose exact placement in that
chain was not fully confirmed.

Hand-chaining an eleven-stage, partially-uncertain internal pipeline blind, with no way to
verify the result against a known-good reference, is exactly the risk the harness's own central
rule exists to prevent: it would mean the harness silently re-implementing (and potentially
mis-implementing) Agent 2's own orchestration logic, rather than simply invoking or consuming
it. The harness therefore **consumes** Agent 2's own already-real, already-committed output
artifact for the `sce00061` network (the same artifact the sibling Agent 3/4/5 repositories
already built their own real test fixtures from) as the Stage 2 result, rather than
live-invoking Agent 2's own runtime — disclosed here, in every stage result's own `warnings`
field for this specific run, and in the completion report. Stage 2 is still fully validated:
the harness parses it, checks its own declared `contract_version`, and computes its checksum,
exactly like every other stage's output.

## The contract-version re-stamping adapters

A related, smaller finding from the same investigation: Agent 3, Agent 4, and Agent 5 each
independently declared their own name for what is, today, structurally the identical
`agent2_model` artifact shape (`"agent2-to-agent3-v1"`, `"agent2-agent3-to-agent4-v1"`,
`"agent2-agent4-to-agent5-v1"` respectively) — there is no single canonical version string the
one real artifact Agent 2 actually produces can simultaneously satisfy for all three consumers,
because no producer-side function in Agent 2 currently stamps a consumer-specific version.
Neither Agent 4's nor Agent 5's own handoff code actually enforces this field today (both are
documented Version 1 no-op placeholders in their own source). `app.harness.adapters` re-stamps
`agent2_model.contract_version` to the exact value each specific downstream consumer documents
as its own expectation when building that consumer's input artifact — never touching any other
field (every species, reaction, parameter, kinetic law, and model assumption is passed through
completely unmodified) — see `docs/02_contract_version_matrix.md` for the full detail and the
docstring on `app.harness.adapters._restamp_contract_version` for the complete rationale.

## Fixture B's own, separately disclosed scope decision

For the fully synthetic fixture, Agent 1's own runtime is not invoked either (no real
literature exists to curate for a hand-authored ground-truth system), and Agent 2's real
assembly pipeline is not invoked for the same reason the real-fixture case above avoids
hand-chaining it blind — doing so for entirely novel, synthetic input would be strictly riskier
than for the real case, where at least a known-good reference artifact exists to fall back on.
Fixture B's own ground-truth model is supplied directly as a hand-authored `agent2_model`
artifact (`tests/fixtures/synthetic_agent2_model.json`), and Agent 3, Agent 4, and Agent 5 are
genuinely, live invoked against it — exercising real calibration, real validation, and real
experimental-design ranking against a model whose true parameters are known by construction.

## Every stage's own artifact is written before the next stage runs

`app.harness.pipeline.run_workflow` writes `stageN_output.json` (and, for Agent 4/5,
`stageN_input.json`) to the run's own stage directory immediately after that stage completes,
before the next stage is ever invoked — see `docs/03_artifact_directory_layout.md`. A contract-
version check runs against the just-written artifact before the next stage's subprocess is
started; a mismatch stops the run immediately (see `docs/04_failure_semantics.md`).
