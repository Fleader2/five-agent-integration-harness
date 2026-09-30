# Contract / Version Matrix

Every value below was read directly from that agent's own committed `version.py` (or, for
Agent 1, its `app/agent1/types.py`) — the harness never invents a version number.

| Boundary | Artifact field checked | Expected value | Source of truth |
|---|---|---|---|
| Agent 1 → Agent 2 | `contract_version` | `1.5` | `agent1-biochemical-curator/app/agent1/types.py` (`AGENT1_CONTRACT_VERSION`); cross-checked against `agent2-antimony-builder/app/agent2/version.py`'s own `AGENT1_HANDOFF_VERSION` (currently equal — `1.5`). |
| Agent 2 → Agent 3 | `contract_version` | `agent2-to-agent3-v1` | `agent3-simulation-diagnostics/app/agent3/version.py` (`AGENT2_HANDOFF_CONTRACT_VERSION`). |
| Agent 2/3 → Agent 4 | `agent2_model.contract_version` | `agent2-agent3-to-agent4-v1` | `agent4-calibration-estimator/app/agent4/version.py` (`AGENT4_HANDOFF_CONTRACT_VERSION`). |
| Agent 2/4 → Agent 5 | `agent2_model.contract_version` | `agent2-agent4-to-agent5-v1` | `agent5-validation-experimental-design/app/agent5/version.py` (`AGENT5_HANDOFF_CONTRACT_VERSION`). |

Each agent's own output/report contract version (not itself gated by any downstream check, but
recorded on every `WorkflowStageResult` for traceability):

| Agent | Own contract version | Source |
|---|---|---|
| Agent 2 | `0.12` | `AGENT2_CONTRACT_VERSION` |
| Agent 3 | `0.1` | `AGENT3_CONTRACT_VERSION` |
| Agent 4 | `0.1` | `AGENT4_CONTRACT_VERSION` |
| Agent 5 | `0.1` | `AGENT5_CONTRACT_VERSION` |

## A genuine finding: one artifact, three different "expected" names

The single physical `agent2_model` artifact Agent 2 actually produces is consumed, unmodified
in every field except `contract_version`, by three different downstream agents — each of which
independently invented its own name for what its own documentation calls "the Agent 2 handoff
contract," even though the shape those three names describe is, today, identical. This is
disclosed prominently here and in `docs/01_orchestration_architecture.md` as a genuine
cross-repository finding this integration exercise surfaced, not a harness defect: see
`app.harness.adapters._restamp_contract_version`'s own docstring for the full reasoning and the
confirmation that neither Agent 4's nor Agent 5's own runtime code currently enforces this
field at all (both are documented Version 1 no-op placeholders).

## Enforcement point

`app.harness.contracts.check_contract_version` is called immediately after each producing
stage's own output artifact is written, and **before** the harness ever invokes the next
stage's subprocess. A mismatch (including a completely missing field — never treated as "no
opinion, assume compatible") sets that boundary's stage result to
`WorkflowStatus.CONTRACT_MISMATCH` and the run stops there; no downstream subprocess is ever
started against an artifact shape it was not built to expect.
