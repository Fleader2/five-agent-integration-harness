# Contract / Version Matrix

Every value below was read directly from that agent's own committed `version.py` (or, for
Agent 1, its `app/agent1/types.py`) — the harness never invents a version number.

**Five-Agent Workflow V1 Hardening increment:** Agent 2 → Agent 3, Agent 2/3 → Agent 4, and
Agent 2/4 → Agent 5 all now expect the identical canonical value,
`AGENT2_DOWNSTREAM_CONTRACT_VERSION = "agent2-downstream-v1"`, read from Agent 2's own
`agent2-antimony-builder/app/agent2/version.py`. Agents 3, 4, and 5's own version constants
(`AGENT3_EXPECTED_AGENT2_VERSION`, `AGENT4_EXPECTED_HANDOFF_VERSION`,
`AGENT5_EXPECTED_HANDOFF_VERSION`) are now literal aliases of this one harness-side constant,
and no boundary performs any re-stamping (see `docs/01_orchestration_architecture.md`).

| Boundary | Artifact field checked | Expected value | Source of truth |
|---|---|---|---|
| Agent 1 → Agent 2 | `contract_version` | `1.5` | `agent1-biochemical-curator/app/agent1/types.py` (`AGENT1_CONTRACT_VERSION`); cross-checked against `agent2-antimony-builder/app/agent2/version.py`'s own `AGENT1_HANDOFF_VERSION` (currently equal — `1.5`). |
| Agent 2 → Agent 3 | `contract_version` | `agent2-downstream-v1` | `agent3-simulation-diagnostics/app/agent3/version.py` (`AGENT2_HANDOFF_CONTRACT_VERSION`), itself equal to Agent 2's own `AGENT2_DOWNSTREAM_CONTRACT_VERSION`. |
| Agent 2/3 → Agent 4 | `agent2_model.contract_version` | `agent2-downstream-v1` | `agent4-calibration-estimator/app/agent4/version.py` (`AGENT4_HANDOFF_CONTRACT_VERSION`), same canonical value. |
| Agent 2/4 → Agent 5 | `agent2_model.contract_version` | `agent2-downstream-v1` | `agent5-validation-experimental-design/app/agent5/version.py` (`AGENT5_HANDOFF_CONTRACT_VERSION`), same canonical value. |

Each agent's own output/report contract version (not itself gated by any downstream check, but
recorded on every `WorkflowStageResult` for traceability):

| Agent | Own contract version | Source |
|---|---|---|
| Agent 2 | `0.12` | `AGENT2_CONTRACT_VERSION` |
| Agent 3 | `0.1` | `AGENT3_CONTRACT_VERSION` |
| Agent 4 | `0.1` | `AGENT4_CONTRACT_VERSION` |
| Agent 5 | `0.1` | `AGENT5_CONTRACT_VERSION` |

## A genuine finding, now resolved: one artifact, three different "expected" names

Before the Five-Agent Workflow V1 Hardening increment, the single physical `agent2_model`
artifact Agent 2 actually produced was consumed, unmodified in every field except
`contract_version`, by three different downstream agents — each of which had independently
invented its own name for what its own documentation called "the Agent 2 handoff contract," even
though the shape those three names described was, already, identical. This was a genuine
cross-repository finding the original integration exercise surfaced, not a harness defect, and
the pre-hardening harness worked around it with a re-stamping adapter
(`app.harness.adapters._restamp_contract_version`).

This increment resolves the finding at its source rather than continuing to work around it:
Agent 2 itself now emits one canonical name (`AGENT2_DOWNSTREAM_CONTRACT_VERSION =
"agent2-downstream-v1"`), and Agents 3, 4, and 5 were each migrated to expect that exact string
(see each repository's own `docs/02_*_contract.md` for its own "Five-Agent Workflow V1 Hardening
increment" paragraph). The re-stamping adapter has been deleted; nothing in this harness rewrites
a contract-version field anywhere, and `app.harness.invariants.check_no_contract_version_restamping`
checks this end to end on every run.

## Enforcement point

`app.harness.contracts.check_contract_version` is called immediately after each producing
stage's own output artifact is written, and **before** the harness ever invokes the next
stage's subprocess. A mismatch (including a completely missing field — never treated as "no
opinion, assume compatible") sets that boundary's stage result to
`WorkflowStatus.CONTRACT_MISMATCH` and the run stops there; no downstream subprocess is ever
started against an artifact shape it was not built to expect.
