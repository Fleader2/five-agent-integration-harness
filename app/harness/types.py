"""The harness's own output contract: workflow request/stage-result/report types.

Every type here is a plain, frozen, JSON-friendly dataclass -- consistent with every agent
repository in this project's own family, even though the harness itself has no runtime
dependency on any of them (see ``docs/01_orchestration_architecture.md`` for why: every agent
is invoked as a separate subprocess in its own venv, and the harness's own code never imports
any agent's Python package).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class WorkflowStatus(StrEnum):
    """The outcome of one stage, or of an entire workflow run.

    * ``SUCCESS`` -- every stage ran, and no stage reported a data gap serious enough to be
      worth flagging at the workflow level (a stage can still carry warnings).
    * ``SUCCESS_WITH_EXPECTED_DATA_GAPS`` -- every stage ran to completion, but at least one
      stage honestly reported a data-insufficiency outcome it is itself designed to report
      (e.g. Agent 4's own ``INSUFFICIENT_DATA``, Agent 5's own
      ``INSUFFICIENT_VALIDATION_DATA``) -- this is a **successful integration run**: the
      workflow completed, cleanly, and told the truth. Never conflated with ``SUCCESS`` (a
      reader must be able to tell "everything actually worked end to end" from "everything
      worked, but there wasn't enough real data to calibrate/validate against").
    * ``CONTRACT_MISMATCH`` -- a producing stage's own declared contract version did not match
      what the consuming stage's own code expects -- detected *before* the consuming stage is
      ever invoked (see ``app.harness.contracts``).
    * ``AGENT_STAGE_FAILED`` -- a stage's own subprocess ran but exited with a genuine failure
      (a non-zero exit code from an uncaught exception in that agent's own code, not an honest
      data-outcome the agent itself reports as data).
    * ``INVALID_ARTIFACT`` -- a stage's own output file could not be parsed as JSON, or failed
      the harness's own minimal structural check (e.g. missing a required top-level key) before
      it could even be handed to the next stage.
    * ``BLOCKED`` -- the run could not proceed past a stage for a reason outside any single
      agent's own control (e.g. that agent's venv does not exist, a required external resource
      such as a database is unreachable).
    """

    SUCCESS = "SUCCESS"
    SUCCESS_WITH_EXPECTED_DATA_GAPS = "SUCCESS_WITH_EXPECTED_DATA_GAPS"
    CONTRACT_MISMATCH = "CONTRACT_MISMATCH"
    AGENT_STAGE_FAILED = "AGENT_STAGE_FAILED"
    INVALID_ARTIFACT = "INVALID_ARTIFACT"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True, slots=True)
class WorkflowStageResult:
    """The complete, traceable record of one stage's own attempted execution."""

    stage_name: str
    agent_label: str
    agent_package_version: str | None
    declared_contract_version: str | None
    expected_contract_version: str | None
    input_artifact_path: str | None
    output_artifact_path: str | None
    input_checksum: str | None
    output_checksum: str | None
    status: WorkflowStatus
    warnings: tuple[str, ...]
    findings_summary: tuple[str, ...]
    elapsed_seconds: float | None
    message: str | None


@dataclass(frozen=True, slots=True)
class WorkflowRunRequest:
    """One complete, explicit request to run the five-agent workflow against one fixture."""

    run_id: str
    fixture_name: str
    stage_directory: str
    stop_on_stage_failure: bool = True


@dataclass(frozen=True, slots=True)
class InvariantCheckResult:
    """One end-to-end invariant check performed across the whole gathered set of stage
    artifacts -- never a per-stage check (those are each stage's own
    ``WorkflowStageResult.warnings``/``findings_summary``)."""

    check_id: str
    passed: bool
    description: str
    details: str


@dataclass(frozen=True, slots=True)
class FiveAgentWorkflowReport:
    """The single, top-level structured output of one harness run."""

    report_id: str
    run_id: str
    fixture_name: str
    harness_contract_version: str
    overall_status: WorkflowStatus
    stages: tuple[WorkflowStageResult, ...]
    invariant_checks: tuple[InvariantCheckResult, ...]
    total_elapsed_seconds: float | None
    sufficiency_note: str


__all__ = [
    "FiveAgentWorkflowReport",
    "InvariantCheckResult",
    "WorkflowRunRequest",
    "WorkflowStageResult",
    "WorkflowStatus",
]
