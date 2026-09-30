# What Constitutes Version 1 Workflow Success

## The central distinction this whole harness exists to make

A workflow run can "succeed" in two qualitatively different ways, and Version 1's own single
most important job is to never let a reader confuse them:

1. **Everything worked, with real data throughout** (`WorkflowStatus.SUCCESS`) — every stage
   ran, every stage's own output represents a genuine, data-backed result.
2. **Everything worked, and honestly told you there wasn't enough real data**
   (`WorkflowStatus.SUCCESS_WITH_EXPECTED_DATA_GAPS`) — every stage ran, every contract was
   satisfied, every subprocess exited cleanly, and at least one stage's own status is itself a
   designed, first-class data-insufficiency outcome (not a crash, not a guess, not a fabricated
   number).

Both are genuine integration-test successes. Collapsing (2) into (1) would misrepresent an
honest "we don't have the data" as "the science is done." Collapsing (2) into a failure status
would punish an agent for telling the truth. Version 1's status precedence (`docs/
04_failure_semantics.md`) is built specifically so neither ever happens by accident.

## Fixture A (real `sce00061`) — success means `SUCCESS_WITH_EXPECTED_DATA_GAPS`

This fixture is considered **fully successful** when, and only when:

- Agent 1 genuinely, live curates the real yeast fatty-acid-biosynthesis data (38 reactions, 216
  kinetic measurements) — not a cached/fabricated stand-in.
- Agent 2's own already-real output artifact for this exact network parses successfully and
  reports `readiness=EXECUTABLE`, and the live `translate_agent1_view_to_agent2` boundary check
  against the freshly-curated Agent 1 view passes.
- Agent 3 genuinely, live simulates/diagnoses the model, producing its own real findings
  (including the real, reproducible `STEADY_STATE_NOT_FOUND` result this specific model is known
  to produce, given its own missing initial conditions).
- Agent 4 genuinely, live attempts calibration and **honestly reports
  `CalibrationStatus.INSUFFICIENT_DATA`** — because no real yeast calibration observation exists
  — rather than either crashing or fabricating a fit against invented data.
- Agent 5 genuinely, live attempts validation and **honestly reports
  `ValidationStatus.INSUFFICIENT_VALIDATION_DATA`** for the identical reason.
- Every end-to-end invariant check passes (identifier traceability, fixed-parameter
  immutability, calibrated-value distinguishability, evidence-provenance survival, no mutation
  of the Agent 2 model, validation never feeding back into calibration).

If any of the above instead shows a crash, a contract mismatch, or — the one outcome that would
actually represent *failure* of this harness's own central rule — a fabricated calibration or
validation result obtained by inventing yeast observation data, Fixture A has **not** succeeded,
regardless of what `overall_status` a bug might otherwise produce.

## Fixture B (synthetic ground truth) — success means full `SUCCESS`, with real recovery

This fixture is considered **fully successful** when, and only when:

- The hand-authored, known-ground-truth network (`S1 -> S2 -> S3 -> S4`, true rates `k1=0.5`,
  `k2=0.2`, `k3=0.1`) is genuinely, live simulated by Agent 3.
- Agent 4 genuinely, live recovers `k1` and `k2` to within a small fraction of their true values
  from supplied synthetic training observations that structurally constrain them — **and**
  correctly flags `k3` (deliberately unconstrained by that same training data) with a real
  `LOW_SENSITIVITY` identifiability finding, rather than reporting a falsely-confident point
  estimate for it.
- Agent 5 genuinely, live validates the calibrated model against held-out synthetic
  observations, reports acceptable generalization (no spurious overfit warning), and **ranks the
  known-informative candidate experiment (measuring the otherwise-unobserved `S4`, the species
  most sensitive to the poorly-identified `k3`) at or near the top of its own scored
  recommendations** — confirmed, in this repository's own run, to land at rank 0.
- Every end-to-end invariant check passes, identically to Fixture A's own list.

Because this fixture's own ground truth is known by construction, a wrong parameter recovery, a
missed identifiability flag, or a poorly-ranked informative experiment would be a genuine,
detectable defect in Agent 4 or Agent 5's own real logic — never explained away as "expected,"
the way Fixture A's data gaps are.

## What Version 1 completion does NOT claim

- It does not claim Agent 2's full internal assembly pipeline has been verified end to end live
  (a disclosed, documented scope limitation — see `docs/01_orchestration_architecture.md`).
- It does not claim the real `sce00061` model is scientifically validated, or even that it is
  ready for real calibration — only that the workflow chain around it is.
- It does not claim full Bayesian/joint-optimal experimental design (Agent 5's own scoring
  method is a disclosed, modest, diagonal sensitivity proxy — see Agent 5's own `docs/
  04_experimental_design_scoring_policy.md`).
- It does not claim every possible contract-boundary edge case has been tested — only the ones
  enumerated in `docs/04_failure_semantics.md` and exercised by this repository's own test
  suite.
