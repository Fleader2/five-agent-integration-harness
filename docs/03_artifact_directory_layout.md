# Artifact Directory Layout

Every run writes to its own directory, `artifacts/runs/<run_id>/` (gitignored — regenerable by
re-running the fixture; the fixture *inputs* under `tests/fixtures/` are checked in and are the
actual reproducible evidence).

```
artifacts/runs/<run_id>/
  stage1_output.json      Agent 1's own real, live-queried Agent1CuratedKnowledgeView
                          (real-yeast fixture only; absent for the synthetic fixture)
  stage2_output.json      The agent2_model artifact this run used (either copied from an
                          already-real committed artifact, or the synthetic ground-truth model)
  stage3_output.json      Agent 3's own full Agent3Report
  stage4_input.json       {"agent2_model": ..., "agent3_diagnostics": ...} -- Agent 4's own
                          handoff contract, built by app.harness.adapters.build_agent4_handoff
  stage4_request.json     The CalibrationRequest this run supplied to Agent 4
  stage4_output.json      Agent 4's own full Agent4Report
  stage5_input.json       {"agent2_model": ..., "agent4_report": ...} -- Agent 5's own handoff
                          contract, built by app.harness.adapters.build_agent5_handoff
  stage5_request.json     The ValidationRequest this run supplied to Agent 5
  stage5_output.json      Agent 5's own full Agent5Report
  workflow_report.json    The top-level FiveAgentWorkflowReport for this run
```

Every `stageN_output.json`/`stageN_input.json` file's own SHA-256 checksum is recorded on its
corresponding `WorkflowStageResult.output_checksum`/`.input_checksum` — the harness's own
"immutable artifact identifier" mechanism (`app.harness.checksums`). Two runs against the same
fixture that produce byte-identical artifacts will always show identical checksums; any
unexpected difference is immediately visible without diffing the full JSON by hand.

## Fixture input files (checked in, under `tests/fixtures/`)

| File | Used by |
|---|---|
| `sce00061_agent1_curated_knowledge_view.json` | A real, freshly-captured (this session) copy of Agent 1's own live-queried output for the real organism -- kept as a reference/fallback artifact; a fresh live run re-queries the database directly rather than reading this file |
| `sce00061_agent2_model.json` | Fixture A's Stage 2 (consumed, not regenerated) |
| `sce00061_calibration_request.json` | Fixture A's Stage 4 request |
| `sce00061_validation_request.json` | Fixture A's Stage 5 request |
| `synthetic_agent2_model.json` | Fixture B's Stage 2 input |
| `synthetic_stage4_request.json` | Fixture B's Stage 4 request (train observations + 3 targets) |
| `synthetic_stage5_request.json` | Fixture B's Stage 5 request (held-out observations) |
| `synthetic_ground_truth_manifest.json` | The true `k1`/`k2`/`k3` values, for comparison in the completion report and tests |

## Why `artifacts/runs/` is gitignored but `tests/fixtures/` is not

`tests/fixtures/` holds the *inputs* a fixture run starts from — these are small, deterministic,
and are exactly what makes a fixture run reproducible; they belong in version control the same
way every sibling repository's own `tests/fixtures/*.json` does. `artifacts/runs/<run_id>/`
holds what a specific run *produced* — regenerable at any time by re-running
`scripts/run_fixture_a.py`/`scripts/run_fixture_b.py`, and potentially large (Fixture A's real
`agent2_model` artifact alone is several hundred kilobytes) — committing every run's own output
would bloat the repository with regenerable data.
