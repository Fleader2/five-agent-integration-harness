"""The Version 1 five-agent orchestration workflow.

``Agent 1 -> Agent 2 -> Agent 3 -> Agent 4 -> Agent 5``

Every stage writes its own output artifact to a clearly-named file in the run's own stage
directory before the next stage is ever invoked. A producing stage's own declared contract
version is checked against what the consuming stage's own code expects *before* that consuming
stage runs -- a mismatch stops the run immediately (``WorkflowStatus.CONTRACT_MISMATCH``),
never silently proceeding against a shape the downstream agent was not built to expect.

**Five-Agent Workflow V1 Hardening increment**: Stage 2 (Agent 2) is now **always** a genuine,
live subprocess invocation of Agent 2's own canonical orchestration entrypoint
(``app.agent2.pipeline.run_agent2_pipeline``, via ``runners/run_agent2.py``) for both canonical
fixtures -- never a copy of a pre-existing artifact. ``app.harness.adapters`` no longer
re-stamps any field; the ``agent2_model`` dict every downstream stage receives is the exact same
object Stage 2 itself produced.
"""

from __future__ import annotations

import json
import shutil
import time
import uuid
from collections.abc import Callable
from pathlib import Path

from app.harness import repo_paths
from app.harness.adapters import build_agent4_handoff, build_agent5_handoff
from app.harness.checksums import sha256_of_file
from app.harness.contracts import check_contract_version
from app.harness.invariants import run_invariant_checks
from app.harness.subprocess_runner import run_stage_subprocess
from app.harness.types import (
    FiveAgentWorkflowReport,
    WorkflowRunRequest,
    WorkflowStageResult,
    WorkflowStatus,
)
from app.harness.version import CONTRACT_VERSION_MATRIX, HARNESS_CONTRACT_VERSION

_RUNNERS_DIR = Path(__file__).resolve().parent / "runners"


def _stage_dir(request: WorkflowRunRequest) -> Path:
    d = Path(request.stage_directory)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _blocked_result(stage_name: str, agent_label: str, message: str) -> WorkflowStageResult:
    return WorkflowStageResult(
        stage_name=stage_name,
        agent_label=agent_label,
        agent_package_version=None,
        declared_contract_version=None,
        expected_contract_version=None,
        input_artifact_path=None,
        output_artifact_path=None,
        input_checksum=None,
        output_checksum=None,
        status=WorkflowStatus.BLOCKED,
        warnings=(),
        findings_summary=(),
        elapsed_seconds=None,
        message=message,
    )


def _contract_mismatch_result(
    stage_name: str, agent_label: str, boundary_name: str, expected: str, actual: str | None
) -> WorkflowStageResult:
    return WorkflowStageResult(
        stage_name=stage_name,
        agent_label=agent_label,
        agent_package_version=None,
        declared_contract_version=actual,
        expected_contract_version=expected,
        input_artifact_path=None,
        output_artifact_path=None,
        input_checksum=None,
        output_checksum=None,
        status=WorkflowStatus.CONTRACT_MISMATCH,
        warnings=(),
        findings_summary=(),
        elapsed_seconds=None,
        message=(
            f"Contract mismatch at boundary {boundary_name!r}: expected contract_version "
            f"{expected!r}, got {actual!r}. Stopping before invoking the downstream stage."
        ),
    )


def _agent_stage_failed_result(
    stage_name: str,
    agent_label: str,
    outcome,
    input_path: Path | None,
) -> WorkflowStageResult:
    return WorkflowStageResult(
        stage_name=stage_name,
        agent_label=agent_label,
        agent_package_version=None,
        declared_contract_version=None,
        expected_contract_version=None,
        input_artifact_path=str(input_path) if input_path else None,
        output_artifact_path=None,
        input_checksum=sha256_of_file(input_path) if input_path and input_path.is_file() else None,
        output_checksum=None,
        status=WorkflowStatus.AGENT_STAGE_FAILED,
        warnings=(),
        findings_summary=(),
        elapsed_seconds=outcome.elapsed_seconds,
        message=(
            f"{agent_label} stage exited with code {outcome.returncode}.\n"
            f"stdout:\n{outcome.stdout}\nstderr:\n{outcome.stderr}"
        ),
    )


def _invalid_json_result(
    stage_name: str,
    agent_label: str,
    outcome,
    input_path: Path | None,
    output_path: Path,
    exc: Exception,
) -> WorkflowStageResult:
    return WorkflowStageResult(
        stage_name=stage_name,
        agent_label=agent_label,
        agent_package_version=None,
        declared_contract_version=None,
        expected_contract_version=None,
        input_artifact_path=str(input_path) if input_path else None,
        output_artifact_path=str(output_path),
        input_checksum=sha256_of_file(input_path) if input_path and input_path.is_file() else None,
        output_checksum=None,
        status=WorkflowStatus.INVALID_ARTIFACT,
        warnings=(),
        findings_summary=(),
        elapsed_seconds=outcome.elapsed_seconds,
        message=f"Output artifact could not be parsed as JSON: {exc}",
    )


def _run_subprocess_stage(
    *,
    stage_name: str,
    agent_label: str,
    repo: repo_paths.AgentRepo,
    script_name: str,
    args: list[str],
    output_path: Path,
    input_path: Path | None,
    findings_extractor,
) -> WorkflowStageResult:
    unavailable = repo_paths.check_repo_available(repo)
    if unavailable is not None:
        return _blocked_result(stage_name, agent_label, unavailable)

    outcome = run_stage_subprocess(
        venv_python=repo.venv_python,
        script_path=_RUNNERS_DIR / script_name,
        cwd=repo.repo_dir,
        args=args,
    )

    if outcome.returncode != 0 or not output_path.is_file():
        return _agent_stage_failed_result(stage_name, agent_label, outcome, input_path)

    try:
        with open(output_path) as f:
            output_data = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        return _invalid_json_result(stage_name, agent_label, outcome, input_path, output_path, exc)

    status, findings = findings_extractor(output_data)
    return WorkflowStageResult(
        stage_name=stage_name,
        agent_label=agent_label,
        agent_package_version=None,
        declared_contract_version=None,
        expected_contract_version=None,
        input_artifact_path=str(input_path) if input_path else None,
        output_artifact_path=str(output_path),
        input_checksum=sha256_of_file(input_path) if input_path and input_path.is_file() else None,
        output_checksum=sha256_of_file(output_path),
        status=status,
        warnings=(),
        findings_summary=findings,
        elapsed_seconds=outcome.elapsed_seconds,
        message=None,
    )


#: Agent 3's own ``SimulationStatus`` values that represent an honest, expected data-gap
#: outcome (e.g. a steady state could not be found given missing initial conditions) --
#: never a stage failure, and never silently reported as a clean ``SUCCESS`` either.
_AGENT3_EXPECTED_DATA_GAP_STATUSES = frozenset({"STEADY_STATE_NOT_FOUND"})


def _agent2_findings(data: dict) -> tuple[WorkflowStatus, tuple[str, ...]]:
    findings = (
        f"species={len(data.get('species', []))}",
        f"reactions={len(data.get('reactions', []))}",
        f"parameters={len(data.get('parameters', []))}",
        f"readiness={data.get('readiness')}",
    )
    return WorkflowStatus.SUCCESS, findings


def _agent3_findings(data: dict) -> tuple[WorkflowStatus, tuple[str, ...]]:
    overall = data["overall_status"]
    findings = (
        f"overall_status={overall}",
        *(f"{f['finding_id']}:{f['severity']}" for f in data.get("diagnostics", [])),
    )
    status = (
        WorkflowStatus.SUCCESS_WITH_EXPECTED_DATA_GAPS
        if overall in _AGENT3_EXPECTED_DATA_GAP_STATUSES
        else WorkflowStatus.SUCCESS
    )
    return status, findings


def _agent4_findings(data: dict) -> tuple[WorkflowStatus, tuple[str, ...]]:
    calib_status = data["calibration"]["status"]
    findings = (f"calibration_status={calib_status}",)
    status = (
        WorkflowStatus.SUCCESS_WITH_EXPECTED_DATA_GAPS
        if calib_status == "INSUFFICIENT_DATA"
        else WorkflowStatus.SUCCESS
    )
    return status, findings


def _agent5_findings(data: dict) -> tuple[WorkflowStatus, tuple[str, ...]]:
    overall = data["overall_status"]
    findings = (f"overall_status={overall}",)
    status = (
        WorkflowStatus.SUCCESS_WITH_EXPECTED_DATA_GAPS
        if overall == "INSUFFICIENT_VALIDATION_DATA"
        else WorkflowStatus.SUCCESS
    )
    return status, findings


def run_workflow(
    request: WorkflowRunRequest,
    *,
    stage1_organism_id: str | None,
    stage1_synthetic_source: str | Path | None = None,
    stage2_postprocess: Callable[[dict], dict] | None = None,
    stage4_request: dict,
    stage5_request: dict,
) -> FiveAgentWorkflowReport:
    """Run the full five-stage workflow.

    Exactly one of ``stage1_organism_id`` (the real-yeast fixture: a live Agent 1 database
    query) or ``stage1_synthetic_source`` (the synthetic fixture: a hand-authored, static Agent
    1 view JSON file -- no real literature exists for a hand-authored ground-truth system) must
    be given. Stage 2 is, in both cases, a genuine live invocation of Agent 2's own canonical
    orchestration entrypoint against whatever Stage 1 produced.

    ``stage2_postprocess``, when given, is applied to Stage 2's own raw output **before** it is
    written to ``stage2_output.json`` and before any checksum/contract-version check runs
    against it -- used only by the synthetic fixture, to patch in the species initial
    concentrations no increment in the Agent 1 -> Agent 2 pipeline yet populates for any input
    (a genuine, pre-existing, disclosed scope gap, also confirmed on the real `sce00061` model
    -- see ``docs/01_orchestration_architecture.md``). Every other field Stage 2 produced is
    passed through unchanged; the real-yeast fixture never supplies this parameter at all.
    """
    if (stage1_organism_id is None) == (stage1_synthetic_source is None):
        raise ValueError(
            "Exactly one of stage1_organism_id or stage1_synthetic_source must be given."
        )

    report_id = f"harness-report-{uuid.uuid4()}"
    started = time.monotonic()
    stage_dir = _stage_dir(request)
    stages: list[WorkflowStageResult] = []

    # --- Stage 1: Agent 1 -------------------------------------------------------------------
    stage1_output = stage_dir / "stage1_output.json"
    if stage1_organism_id is not None:
        unavailable = repo_paths.check_repo_available(repo_paths.AGENT1)
        if unavailable is not None:
            stages.append(_blocked_result("agent1_curation", "Agent 1", unavailable))
            return _finish(report_id, request, stages, started, stage_dir)
        outcome = run_stage_subprocess(
            venv_python=repo_paths.AGENT1.venv_python,
            script_path=_RUNNERS_DIR / "run_agent1.py",
            cwd=repo_paths.AGENT1.repo_dir,
            args=["--organism-id", stage1_organism_id, "--output", str(stage1_output)],
        )
        if outcome.returncode != 0 or not stage1_output.is_file():
            stages.append(_agent_stage_failed_result("agent1_curation", "Agent 1", outcome, None))
            return _finish(report_id, request, stages, started, stage_dir)
        elapsed = outcome.elapsed_seconds
        warnings: tuple[str, ...] = ()
    else:
        shutil.copy(stage1_synthetic_source, stage1_output)
        elapsed = None
        warnings = (
            "Synthetic fixture: Agent 1's own runtime was not invoked (no real literature "
            "exists for a hand-authored ground-truth system) -- a static, hand-authored Agent "
            "1 view JSON is supplied directly as this stage's own output, then routed through "
            "Agent 2's own real, live, canonical pipeline exactly like the real-yeast fixture. "
            "See docs/01_orchestration_architecture.md for the disclosed rationale.",
        )

    with open(stage1_output) as f:
        stage1_data = json.load(f)
    check1 = check_contract_version(
        stage1_data,
        boundary_name="agent1_to_agent2",
        field_path="contract_version",
        expected_version=CONTRACT_VERSION_MATRIX[0][2],
    )
    stages.append(
        WorkflowStageResult(
            stage_name="agent1_curation",
            agent_label="Agent 1",
            agent_package_version=stage1_data.get("contract_version"),
            declared_contract_version=check1.actual_version,
            expected_contract_version=check1.expected_version,
            input_artifact_path=None,
            output_artifact_path=str(stage1_output),
            input_checksum=None,
            output_checksum=sha256_of_file(stage1_output),
            status=WorkflowStatus.SUCCESS if check1.matches else WorkflowStatus.CONTRACT_MISMATCH,
            warnings=warnings,
            findings_summary=(
                f"reactions={len(stage1_data.get('reactions', []))}",
                f"compounds={len(stage1_data.get('compounds', []))}",
                f"kinetic_measurements={len(stage1_data.get('kinetic_measurements', []))}",
            ),
            elapsed_seconds=elapsed,
            message=None if check1.matches else "Agent 1 output contract_version mismatch.",
        )
    )
    if not check1.matches:
        return _finish(report_id, request, stages, started, stage_dir)

    # --- Stage 2: Agent 2 -- always a genuine, live canonical-pipeline invocation -----------
    stage2_raw_output = stage_dir / "stage2_output_raw.json"
    unavailable = repo_paths.check_repo_available(repo_paths.AGENT2)
    if unavailable is not None:
        stages.append(_blocked_result("agent2_assembly", "Agent 2", unavailable))
        return _finish(report_id, request, stages, started, stage_dir)
    outcome2 = run_stage_subprocess(
        venv_python=repo_paths.AGENT2.venv_python,
        script_path=_RUNNERS_DIR / "run_agent2.py",
        cwd=repo_paths.AGENT2.repo_dir,
        args=["--input", str(stage1_output), "--output", str(stage2_raw_output)],
    )
    if outcome2.returncode != 0 or not stage2_raw_output.is_file():
        stages.append(
            _agent_stage_failed_result("agent2_assembly", "Agent 2", outcome2, stage1_output)
        )
        return _finish(report_id, request, stages, started, stage_dir)

    try:
        with open(stage2_raw_output) as f:
            stage2_data = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        stages.append(
            _invalid_json_result(
                "agent2_assembly", "Agent 2", outcome2, stage1_output, stage2_raw_output, exc
            )
        )
        return _finish(report_id, request, stages, started, stage_dir)

    stage2_warnings: tuple[str, ...] = ()
    if stage2_postprocess is not None:
        stage2_data = stage2_postprocess(stage2_data)
        stage2_warnings = (
            "Synthetic fixture: species initial concentrations were patched onto Agent 2's own "
            "real, live, canonical pipeline output -- no increment in the Agent 1 -> Agent 2 "
            "pipeline yet populates them for any input (a genuine, pre-existing, disclosed "
            "scope gap, also confirmed on the real sce00061 model). Every other field "
            "(species/reactions/kinetic_laws/parameters/antimony structure) is this run's own "
            "real, unmodified Agent 2 pipeline output.",
        )

    stage2_output = stage_dir / "stage2_output.json"
    with open(stage2_output, "w") as f:
        json.dump(stage2_data, f, indent=2)

    check2 = check_contract_version(
        stage2_data,
        boundary_name="agent2_to_agent3",
        field_path="contract_version",
        expected_version=CONTRACT_VERSION_MATRIX[1][2],
    )
    stages.append(
        WorkflowStageResult(
            stage_name="agent2_assembly",
            agent_label="Agent 2",
            agent_package_version=None,
            declared_contract_version=check2.actual_version,
            expected_contract_version=check2.expected_version,
            input_artifact_path=str(stage1_output),
            output_artifact_path=str(stage2_output),
            input_checksum=sha256_of_file(stage1_output),
            output_checksum=sha256_of_file(stage2_output),
            status=WorkflowStatus.SUCCESS if check2.matches else WorkflowStatus.CONTRACT_MISMATCH,
            warnings=stage2_warnings,
            findings_summary=_agent2_findings(stage2_data)[1],
            elapsed_seconds=outcome2.elapsed_seconds,
            message=None if check2.matches else "Agent 2 output contract_version mismatch.",
        )
    )
    if not check2.matches:
        return _finish(report_id, request, stages, started, stage_dir)

    # --- Stage 3: Agent 3 -------------------------------------------------------------------
    stage3_output = stage_dir / "stage3_output.json"
    stages.append(
        _run_subprocess_stage(
            stage_name="agent3_simulation",
            agent_label="Agent 3",
            repo=repo_paths.AGENT3,
            script_name="run_agent3.py",
            args=["--input", str(stage2_output), "--output", str(stage3_output)],
            output_path=stage3_output,
            input_path=stage2_output,
            findings_extractor=_agent3_findings,
        )
    )
    if stages[-1].status not in (
        WorkflowStatus.SUCCESS,
        WorkflowStatus.SUCCESS_WITH_EXPECTED_DATA_GAPS,
    ):
        return _finish(report_id, request, stages, started, stage_dir)
    with open(stage3_output) as f:
        stage3_data = json.load(f)

    # --- Stage 4: Agent 4 --------------------------------------------------------------------
    stage4_handoff = stage_dir / "stage4_input.json"
    stage4_output = stage_dir / "stage4_output.json"
    with open(stage4_handoff, "w") as f:
        json.dump(build_agent4_handoff(stage2_data, stage3_data), f, indent=2)
    check4 = check_contract_version(
        json.loads(stage4_handoff.read_text()),
        boundary_name="agent2_agent3_to_agent4",
        field_path=CONTRACT_VERSION_MATRIX[2][1],
        expected_version=CONTRACT_VERSION_MATRIX[2][2],
    )
    if not check4.matches:
        stages.append(
            _contract_mismatch_result(
                "agent4_calibration",
                "Agent 4",
                "agent2_agent3_to_agent4",
                check4.expected_version,
                check4.actual_version,
            )
        )
        return _finish(report_id, request, stages, started, stage_dir)
    stage4_request_path = stage_dir / "stage4_request.json"
    with open(stage4_request_path, "w") as f:
        json.dump(stage4_request, f, indent=2)
    stages.append(
        _run_subprocess_stage(
            stage_name="agent4_calibration",
            agent_label="Agent 4",
            repo=repo_paths.AGENT4,
            script_name="run_agent4.py",
            args=[
                "--handoff",
                str(stage4_handoff),
                "--request",
                str(stage4_request_path),
                "--output",
                str(stage4_output),
            ],
            output_path=stage4_output,
            input_path=stage4_handoff,
            findings_extractor=_agent4_findings,
        )
    )
    if stages[-1].status not in (
        WorkflowStatus.SUCCESS,
        WorkflowStatus.SUCCESS_WITH_EXPECTED_DATA_GAPS,
    ):
        return _finish(report_id, request, stages, started, stage_dir)
    with open(stage4_output) as f:
        stage4_data = json.load(f)

    # --- Stage 5: Agent 5 ----------------------------------------------------------------------
    stage5_handoff = stage_dir / "stage5_input.json"
    stage5_output = stage_dir / "stage5_output.json"
    with open(stage5_handoff, "w") as f:
        json.dump(build_agent5_handoff(stage2_data, stage4_data), f, indent=2)
    check5 = check_contract_version(
        json.loads(stage5_handoff.read_text()),
        boundary_name="agent2_agent4_to_agent5",
        field_path=CONTRACT_VERSION_MATRIX[3][1],
        expected_version=CONTRACT_VERSION_MATRIX[3][2],
    )
    if not check5.matches:
        stages.append(
            _contract_mismatch_result(
                "agent5_validation",
                "Agent 5",
                "agent2_agent4_to_agent5",
                check5.expected_version,
                check5.actual_version,
            )
        )
        return _finish(report_id, request, stages, started, stage_dir)
    stage5_request_path = stage_dir / "stage5_request.json"
    with open(stage5_request_path, "w") as f:
        json.dump(stage5_request, f, indent=2)
    stages.append(
        _run_subprocess_stage(
            stage_name="agent5_validation",
            agent_label="Agent 5",
            repo=repo_paths.AGENT5,
            script_name="run_agent5.py",
            args=[
                "--handoff",
                str(stage5_handoff),
                "--request",
                str(stage5_request_path),
                "--output",
                str(stage5_output),
            ],
            output_path=stage5_output,
            input_path=stage5_handoff,
            findings_extractor=_agent5_findings,
        )
    )
    return _finish(report_id, request, stages, started, stage_dir)


def _load_json_safely(path: Path | None) -> dict | None:
    """``None`` if ``path`` is unset, missing, or not valid JSON -- never raises. A stage whose
    own artifact failed to parse already reported ``WorkflowStatus.INVALID_ARTIFACT`` for
    itself; this second, independent read (purely for cross-stage invariant checking) must not
    crash the whole report-building step over the same already-disclosed problem."""
    if path is None or not path.is_file():
        return None
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return None


def _finish(
    report_id: str,
    request: WorkflowRunRequest,
    stages: list[WorkflowStageResult],
    started: float,
    stage_dir: Path,
) -> FiveAgentWorkflowReport:
    overall = _determine_overall_status(stages)

    invariant_checks = ()
    stage_by_name = {s.stage_name: s for s in stages}
    agent2_path = (
        Path(stage_by_name["agent2_assembly"].output_artifact_path)
        if "agent2_assembly" in stage_by_name
        and stage_by_name["agent2_assembly"].output_artifact_path
        else None
    )
    stage2_data = _load_json_safely(agent2_path)
    if stage2_data is not None:
        stage3_data = None
        stage4_data = None
        stage5_input_agent2 = None
        stage5_input_agent4 = None
        if (
            "agent3_simulation" in stage_by_name
            and stage_by_name["agent3_simulation"].output_artifact_path
        ):
            stage3_data = _load_json_safely(
                Path(stage_by_name["agent3_simulation"].output_artifact_path)
            )
        if (
            "agent4_calibration" in stage_by_name
            and stage_by_name["agent4_calibration"].output_artifact_path
        ):
            stage4_data = _load_json_safely(
                Path(stage_by_name["agent4_calibration"].output_artifact_path)
            )
        stage5_input_path = stage_dir / "stage5_input.json"
        stage5_input = _load_json_safely(stage5_input_path)
        if stage5_input is not None:
            stage5_input_agent2 = stage5_input.get("agent2_model")
            stage5_input_agent4 = stage5_input.get("agent4_report")
        stage4_input_path = stage_dir / "stage4_input.json"
        stage4_input = _load_json_safely(stage4_input_path)
        stage4_input_agent2 = stage4_input.get("agent2_model") if stage4_input is not None else None
        invariant_checks = run_invariant_checks(
            stage2_output=stage2_data,
            stage3_output=stage3_data,
            stage4_output=stage4_data,
            stage5_input_agent2_model=stage5_input_agent2,
            stage5_input_agent4_report=stage5_input_agent4,
            stage4_input_agent2_model=stage4_input_agent2,
        )
        if any(not c.passed for c in invariant_checks) and overall in (
            WorkflowStatus.SUCCESS,
            WorkflowStatus.SUCCESS_WITH_EXPECTED_DATA_GAPS,
        ):
            overall = WorkflowStatus.INVALID_ARTIFACT

    sufficient_note = _sufficiency_note(overall, stages)
    return FiveAgentWorkflowReport(
        report_id=report_id,
        run_id=request.run_id,
        fixture_name=request.fixture_name,
        harness_contract_version=HARNESS_CONTRACT_VERSION,
        overall_status=overall,
        stages=tuple(stages),
        invariant_checks=invariant_checks,
        total_elapsed_seconds=time.monotonic() - started,
        sufficiency_note=sufficient_note,
    )


def _determine_overall_status(stages: list[WorkflowStageResult]) -> WorkflowStatus:
    if not stages:
        return WorkflowStatus.BLOCKED
    for stage in stages:
        if stage.status in (
            WorkflowStatus.BLOCKED,
            WorkflowStatus.CONTRACT_MISMATCH,
            WorkflowStatus.AGENT_STAGE_FAILED,
            WorkflowStatus.INVALID_ARTIFACT,
        ):
            return stage.status
    if any(s.status is WorkflowStatus.SUCCESS_WITH_EXPECTED_DATA_GAPS for s in stages):
        return WorkflowStatus.SUCCESS_WITH_EXPECTED_DATA_GAPS
    return WorkflowStatus.SUCCESS


def _sufficiency_note(overall: WorkflowStatus, stages: list[WorkflowStageResult]) -> str:
    if overall is WorkflowStatus.SUCCESS:
        return "All five stages completed successfully with no expected data gaps."
    if overall is WorkflowStatus.SUCCESS_WITH_EXPECTED_DATA_GAPS:
        return (
            "All five stages completed; at least one stage honestly reported an expected "
            "data-insufficiency outcome (e.g. INSUFFICIENT_DATA/INSUFFICIENT_VALIDATION_DATA) "
            "rather than a crash -- this is a successful integration run."
        )
    failed = next((s for s in stages if s.status is overall), None)
    stage_name = failed.stage_name if failed else "unknown"
    return f"Workflow stopped at stage {stage_name!r} with status {overall.value}."


__all__ = ["run_workflow"]
