# Workbench <-> Harness Contract

This document describes the one, canonical way the Workbench
(`mechanistic-modeling-workbench`) asks this harness to run the five-agent
workflow, and what it gets back. It adds a request/result contract around
the harness's own pre-existing `app.harness.pipeline.run_workflow`
mechanism -- it introduces no new orchestration logic, no new agent
invocation path, and no scientific logic of any kind.

> The harness orchestrates agents; it does not duplicate agent logic or
> repair outputs.

That rule is unchanged. The Workbench invokes the harness as a consumer of
an already-documented CLI entrypoint, never by reaching into any agent's
database or internal implementation module, and never by reaching into
this harness's own internal modules either.

## Contract types

`app/harness/workbench_contracts.py`:

* `WorkbenchInvocationRequest` -- what the Workbench sends. Minimum
  fields: `run_id`, `project_id`, `subproject_id`, `task_type`,
  `requested_entry_stage`, `contract_version`; optional `model_id`,
  `model_build_request_id`, `agent1_organism_id`,
  `input_artifact_references`, `correlation_id`, `notes`, `submitted_at`.
* `WorkbenchRunResult` -- what the harness reports back. Fields:
  `run_id`, `status` (`SUCCEEDED`/`FAILED`/`CANCELLED`),
  `stages_executed`, `output_artifact_references`,
  `model_artifact_reference`, `agent_contract_versions`, `started_at`,
  `completed_at`, `error` (structured), `summary`, `warnings`,
  `replayed`, `contract_version`.

`WORKBENCH_HARNESS_CONTRACT_VERSION` (currently `"workbench-harness-v1"`)
is this contract's own version -- unrelated to
`app.harness.version.HARNESS_CONTRACT_VERSION` (the harness's own
internal `FiveAgentWorkflowReport` contract) and unrelated to any agent's
own scientific contract version. The Workbench's own copy of these same
types lives in `app/contracts/harness.py` of that repository; the two are
kept in sync by hand, the same way every other contract boundary in this
project's family already works (no repository imports another's Python
package).

## Canonical entrypoint

`scripts/run_workbench_request.py`:

```bash
.venv/bin/python3 scripts/run_workbench_request.py \
    --request /path/to/workbench_invocation_request.json \
    --output /path/to/workbench_run_result.json
```

This is the *only* documented, supported way to invoke this harness on
behalf of the Workbench. It is a thin wrapper: it parses the request,
performs a small number of deterministic pre-flight checks (below), and
then calls the exact same `run_workflow` function `scripts/run_fixture_a.py`
and `scripts/run_fixture_b.py` already call, with the exact same
"run every stage as a real subprocess in that agent's own venv" mechanism.
Nothing about agent invocation itself changed.

### Only one entry stage is implemented

`requested_entry_stage` must equal `"FULL_PIPELINE"`
(`SUPPORTED_ENTRY_STAGE`). The harness's own `run_workflow` runs a fixed
`Agent1 -> Agent2 -> Agent3 -> Agent4 -> Agent5` sequence; it has no
partial/entry-stage execution mode. A request naming any other value is
rejected with `UNSUPPORTED_ENTRY_STAGE` before any agent runs -- this is a
disclosed gap, not a silent fallback to the full pipeline.

### The disclosed `ModelBuildRequest` gap

`model_build_request_id`, when supplied, is recorded in the result's own
`warnings` but has **no effect on execution**. Agent 2 only consumes
`Agent1CuratedKnowledgeViewContract` and has no mechanism to accept a
scoped/partial build request -- confirmed directly against Agent 2's own
code. Until Agent 2 (or a new, explicitly-designed contract) gains that
capability, every Workbench-invoked run builds against the full curated
knowledge view, unscoped, regardless of what `ModelBuildRequest` content
the Workbench may be holding. This is intentional: inventing a new,
unreviewed Agent 2 scientific contract inside this increment would be
exactly the kind of scope creep the project's own architecture audit
exists to prevent.

## Run lifecycle and idempotent replay

Every run is identified by `run_id`, a caller-chosen idempotency key (in
practice, the Workbench's own `RunRecord.id`). The entrypoint writes its
result to `artifacts/runs/<run_id>/workbench_result.json` (gitignored,
exactly like every other run artifact this harness produces) in addition
to the caller's own `--output` path. **Before doing anything else**, the
entrypoint checks whether that file already exists for the given
`run_id`; if so, it is read and returned unchanged, with `replayed=True`
set on the *returned* copy, and no agent is invoked again. A `run_id`
that was already attempted -- whether it succeeded, failed, or was
rejected before any agent ran -- always replays the same outcome. A
genuinely new attempt requires a new `run_id`.

The full, unabridged `FiveAgentWorkflowReport` (the harness's own
pre-existing contract) is still written to
`artifacts/runs/<run_id>/workflow_report.json` on every fresh execution,
exactly as the two fixture scripts already do -- `WorkbenchRunResult` is
a *summary* of that report, never a replacement for it. Anyone needing
per-stage checksums, full findings, or invariant-check detail should read
that file directly.

## Pre-flight rejection order (no agent invoked)

1. Request fails to parse -> `MALFORMED_REQUEST`.
2. A cached result already exists for `run_id` -> replay (see above).
3. `contract_version` != `WORKBENCH_HARNESS_CONTRACT_VERSION` ->
   `CONTRACT_VERSION_MISMATCH`.
4. `requested_entry_stage` != `"FULL_PIPELINE"` ->
   `UNSUPPORTED_ENTRY_STAGE`.
5. Not exactly one of `agent1_organism_id` /
   `input_artifact_references["stage1_synthetic_source"]` is set ->
   `INVALID_STAGE1_INPUT`.
6. `input_artifact_references["stage4_request"]`/`["stage5_request"]`
   missing or unreadable -> `MISSING_INPUT_ARTIFACT`.

Only after all six checks pass does `run_workflow` actually run. If it
fails partway (a `CONTRACT_MISMATCH`/`AGENT_STAGE_FAILED`/
`INVALID_ARTIFACT`/`BLOCKED` `WorkflowStatus`, exactly as already defined
and unchanged by this contract), the result's own `error.code` is
`WORKFLOW_FAILED` and `error.stage_name` names the stage that stopped the
run -- the harness's own existing stage-level semantics, just reshaped
into the Workbench's own result contract.

## Artifact ownership

* Every `output_artifact_references[stage_name]` value is an absolute
  filesystem path into *this* repository's own `artifacts/runs/<run_id>/`
  directory -- this harness creates and owns every one of these files;
  the Workbench only ever stores the path string, never a copy of the
  content.
* `model_artifact_reference` is always exactly
  `output_artifact_references["agent2_assembly"]` when that stage ran --
  Agent 2's own real output file, never re-derived or duplicated.
* Mutability: every artifact under one `run_id`'s own directory is
  write-once by convention (the same convention `run_workflow` already
  follows for every fixture) -- a replayed request never rewrites them.
* No new checksum field was added to this contract: `workflow_report.json`
  already carries a `sha256` of every stage's own input/output file
  (`WorkflowStageResult.input_checksum`/`output_checksum`); a caller
  needing one reads that file rather than this summary.

## No scientific logic added

Nothing in `workbench_contracts.py` or `run_workbench_request.py`
inspects, transforms, or re-derives any agent's own scientific content.
The entrypoint's only "decisions" are the six deterministic, pre-flight
checks above, all about the *shape* of the request, never about biology,
models, simulations, calibration, or validation.
