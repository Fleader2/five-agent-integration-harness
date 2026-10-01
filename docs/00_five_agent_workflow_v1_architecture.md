# Five-Agent Workflow — Version 1 Architecture

This is the top-level map of the hardened Version 1 system: what each repository is, how data
flows between them, which contract versions govern each boundary, and what counts as a
successful run. Every other `docs/*.md` file in this repository goes into more depth on one of
the sections below; this file is the one page a new reader (or a future Version 2 effort) should
start from.

## Repository map

| Repository | Role |
|---|---|
| `agent1-biochemical-curator` | Agent 1 — Biochemical Curator |
| `agent2-antimony-builder` | Agent 2 — Antimony / Mechanistic Model Builder |
| `agent3-simulation-diagnostics` | Agent 3 — Simulation and Diagnostics |
| `agent4-calibration-estimator` | Agent 4 — Calibration and Parameter Estimation |
| `agent5-validation-experimental-design` | Agent 5 — Validation and Experimental Design |
| `five-agent-integration-harness` (this repository) | Integration Harness |

All six repositories live as siblings under the same parent directory. Every agent repository
uses the identical top-level package name `app`, so the harness never imports a sibling agent's
Python package — every stage is run as an isolated OS subprocess, in that agent's own `.venv`,
with that agent's own repository as the working directory (`app.harness.repo_paths`,
`app.harness.subprocess_runner`).

## Canonical workflow

```
Agent 1 -> Agent 2 -> Agent 3 -> Agent 4 -> Agent 5
```

Each arrow is a plain, versioned, JSON-serializable contract — never a Python import across
repositories. `app.harness.pipeline.run_workflow` runs all five stages in order, writing each
stage's own output artifact to the run's own stage directory before the next stage is ever
invoked (see `docs/03_artifact_directory_layout.md`), and stops the run immediately on a
contract-version mismatch, a stage failure, or an invalid artifact (see
`docs/04_failure_semantics.md`).

## Canonical contract/version matrix

| Constant | Value | Declared in |
|---|---|---|
| Agent 1 handoff version (`AGENT1_CONTRACT_VERSION`) | `1.5` | `agent1-biochemical-curator/app/agent1/types.py` |
| Agent 2's own expected Agent 1 version (`AGENT1_HANDOFF_VERSION`) | `1.5` | `agent2-antimony-builder/app/agent2/version.py` |
| Agent 2's own model/Antimony contract (`AGENT2_CONTRACT_VERSION`) | `0.12` | `agent2-antimony-builder/app/agent2/version.py` |
| Agent 2's orchestration policy (`AGENT2_ORCHESTRATION_POLICY_VERSION`) | `agent2-orchestration-v1` | `agent2-antimony-builder/app/agent2/version.py` |
| **Canonical Agent 2 downstream contract** (`AGENT2_DOWNSTREAM_CONTRACT_VERSION`) | **`agent2-downstream-v1`** | `agent2-antimony-builder/app/agent2/version.py` — the one value Agents 3, 4, and 5 all expect unchanged |
| Agent 3's own expected Agent 2 version (`AGENT2_HANDOFF_CONTRACT_VERSION`) | `agent2-downstream-v1` | `agent3-simulation-diagnostics/app/agent3/version.py` |
| Agent 3's own report contract (`AGENT3_CONTRACT_VERSION`) | `0.1` | `agent3-simulation-diagnostics/app/agent3/version.py` |
| Agent 4's own expected handoff version (`AGENT4_HANDOFF_CONTRACT_VERSION`) | `agent2-downstream-v1` | `agent4-calibration-estimator/app/agent4/version.py` |
| Agent 4's own report contract (`AGENT4_CONTRACT_VERSION`) | `0.1` | `agent4-calibration-estimator/app/agent4/version.py` |
| Agent 5's own expected handoff version (`AGENT5_HANDOFF_CONTRACT_VERSION`) | `agent2-downstream-v1` | `agent5-validation-experimental-design/app/agent5/version.py` |
| Agent 5's own report contract (`AGENT5_CONTRACT_VERSION`) | `0.1` | `agent5-validation-experimental-design/app/agent5/version.py` |
| Harness contract/version matrix (`HARNESS_CONTRACT_VERSION`) | `0.2` | `app/harness/version.py` (this repository) |

The harness's own `AGENT3_EXPECTED_AGENT2_VERSION`/`AGENT4_EXPECTED_HANDOFF_VERSION`/
`AGENT5_EXPECTED_HANDOFF_VERSION` are literal Python aliases of
`AGENT2_DOWNSTREAM_CONTRACT_VERSION` — not just three equal strings — so the three downstream
boundaries cannot silently drift apart again. See `docs/02_contract_version_matrix.md` for the
full enforcement detail and the history of the pre-hardening three-divergent-names finding this
replaced.

## Agent responsibility boundaries

| Agent | Consumes | Produces | Explicitly does not |
|---|---|---|---|
| **Agent 1** | Live, already-curated Postgres database (compartments, compounds, reactions, kinetic measurements, enzyme states, evidence) | `Agent1CuratedKnowledgeView` (JSON, `contract_version=1.5`) | Resolve kinetics, build a model, invent a measurement, write to the database |
| **Agent 2** | Agent 1's curated view | The canonical downstream handoff (`contract_version=agent2-downstream-v1`): model/network ids, Antimony text, readiness, compartments/species/reactions, kinetic laws, parameters with provenance/bounds/`fixed`, model assumptions | Simulate, calibrate, validate, invent a kinetic mechanism not supported by evidence or policy |
| **Agent 3** | Agent 2's canonical handoff | `Agent3Report` (diagnostics, heuristic/placeholder parameter ids, sufficiency verdict) | Alter the model, retry with different tolerances, calibrate anything |
| **Agent 4** | Agent 2's canonical handoff + Agent 3's diagnostics view + a `CalibrationRequest` | `Agent4Report` (fitted parameter estimates with original value/source preserved alongside the fitted value, identifiability findings, residuals) | Fit a parameter the request does not explicitly authorize, change a fixed/evidence-backed parameter |
| **Agent 5** | Agent 2's canonical handoff + Agent 4's report + a `ValidationRequest` | `Agent5Report` (held-out validation metrics, ranked candidate experiments) | Mutate the model, recalibrate, feed validation data back into fitting |
| **Integration Harness** | All five agents' own already-committed runner entrypoints | `FiveAgentWorkflowReport` (per-stage results, invariant checks, overall status) | Duplicate any agent's own modeling/calibration/diagnostic logic, silently repair an agent's output |

## Acceptance fixtures

### Fixture A — real `sce00061`

`scripts/run_fixture_a.py`. Expected overall result: **`SUCCESS_WITH_EXPECTED_DATA_GAPS`**.

- Agent 1 performs real, live curation of the yeast fatty-acid-biosynthesis network (38
  reactions, 216 kinetic measurements).
- Agent 2's canonical entrypoint, genuinely live-invoked against that fresh output, produces an
  executable model (`readiness=EXECUTABLE`; 53 species, 38 reactions, 115 parameters).
- Agent 3 reports real diagnostic gaps (`STEADY_STATE_NOT_FOUND`, driven by the genuine,
  disclosed missing-initial-condition scope gap below).
- Agent 4 honestly reports `CalibrationStatus.INSUFFICIENT_DATA` — no real yeast calibration
  observations exist.
- Agent 5 honestly reports `ValidationStatus.INSUFFICIENT_VALIDATION_DATA` for the same reason.

### Fixture B — synthetic ground truth

`scripts/run_fixture_b.py`. Expected overall result: **`SUCCESS`**.

- A synthetic Agent 1 view (`S1 -> S2 -> S3 -> S4`, three true rate constants) is routed through
  the same canonical Agent 2 entrypoint as Fixture A, with one disclosed post-processing patch
  for initial conditions (see below).
- The two identifiable parameters are recovered to within a small fraction of their true values.
- The deliberately unidentifiable third parameter is correctly flagged with a `LOW_SENSITIVITY`
  identifiability finding, never a falsely-confident point estimate.
- Held-out validation succeeds (no spurious overfit warning).
- The known informative experiment (measuring the otherwise-unobserved species) ranks first
  among Agent 5's own scored recommendations.

See `docs/06_version1_success_criteria.md` for the full detail behind both results.

## V1 invariants

Checked automatically at the end of every run (`app.harness.invariants.run_invariant_checks`):

1. **Identifier traceability** — every species/reaction/parameter id a downstream stage
   references actually exists in Agent 2's own model.
2. **Provenance preservation** — every Agent 4 estimate's `original_source` matches what Agent 2
   originally declared; never silently re-labeled downstream.
3. **Fixed/evidence-backed values not silently changed** — no parameter Agent 2 declared
   `fixed=True` is ever calibrated.
4. **Calibrated values distinguishable from originals** — every estimate carries its original
   value/source *and* its fitted value side by side, never overwritten in place.
5. **Validation never feeds back into calibration** — Agent 5's own input parameter estimates are
   byte-identical to what Agent 4 actually produced.
6. **Agent 5 does not mutate the model** — Agent 5's own input Antimony text is byte-identical to
   Agent 2's output.
7. **No invented biological observations** — an honest data gap (`INSUFFICIENT_DATA`,
   `INSUFFICIENT_VALIDATION_DATA`, `STEADY_STATE_NOT_FOUND`) is never papered over with a
   fabricated measurement.
8. **One unchanged Agent 2 artifact used by all downstream consumers** — the same content
   checksum for the `agent2_model` Stage 3 consumes directly and the `agent2_model` embedded in
   Stage 4's and Stage 5's own input handoffs (`check_agent2_artifact_checksum_consistent`).
9. **No contract-version re-stamping** — Agent 2's own declared `contract_version` is identical
   everywhere it appears downstream; the harness performs no re-stamping at any boundary
   (`check_no_contract_version_restamping`).

Invariants 1–7 predate this hardening increment; invariants 8–9 were added by it, specifically to
make the two resolved integration debts (described below) permanent, checked properties of every
future run rather than one-time claims.

## Canonical baseline note

The **official hardened Agent 2 pipeline** is `app.agent2.pipeline.run_agent2_pipeline`
(`agent2-antimony-builder`), invoked by this harness's `app/harness/runners/run_agent2.py` for
both canonical fixtures. It is the one authoritative source of Agent 2 output for all future
regression comparisons.

Earlier, pre-hardening results reporting **109 parameters** (88 heuristic, 21 protected) for the
real `sce00061` model came from an **incomplete** orchestration path that never ran Agent 2's own
reaction-context resolution or enzyme-concentration/enzyme-state-dynamics stages. The canonical
pipeline exercises the full, correct stage sequence (including the two-pass
`declare_parameters`/`assess_boundaries`/`decompose_network` wiring) and genuinely declares
**115 parameters** (107 heuristic, 8 protected: 7 `AI_PREDICTED` + 1 `LITERATURE_DERIVED`) for the
identical real model. This is a richer, more correct result, not a regression — any future
comparison against the pre-hardening 109-parameter figure is comparing against a known-incomplete
baseline and should be retired in favor of the canonical pipeline's own output.

One disclosed scope gap remains, unchanged by this hardening increment: Agent 2's own pipeline
does not yet populate species initial concentrations or compartment initial volume for *any*
input. This is why Fixture A's own Agent 3 stage reports `STEADY_STATE_NOT_FOUND`, and why
Fixture B requires one minimal, disclosed post-processing patch
(`app.harness.synthetic_fixture.patch_synthetic_ground_truth_initial_conditions`) before it can
simulate from its intended starting state. See `docs/01_orchestration_architecture.md` for the
full detail.
