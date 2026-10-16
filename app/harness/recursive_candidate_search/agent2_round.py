"""Invoking one round of Agent 2's own candidate-search orchestration as an isolated
subprocess (``run_agent2_candidate_search_round.py``) -- the real, production implementation of
the ``invoke_round`` callable ``orchestration.run_recursive_candidate_search`` takes (tests
inject a fast, deterministic fake instead; see that module's own docstring).

``attach_modularization`` (Automatic Hierarchical Recursive Modularization increment,
optional): a previously-accepted modularization's own structure (module ids + per-module
content-key pairs), exactly as this harness already received it back from an earlier call's
own ``round_summary`` -- re-attached to the freshly-rebuilt model before
``--seed-modularization-id``/``--submodel-module-id`` are resolved, so a *descendant* level can
materialize a submodel from one of *that* modularization's own modules. Never invents or
re-derives membership -- see ``app.harness.hierarchical_recursion``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.harness.recursive_candidate_search.errors import RecursiveCandidateSearchError
from app.harness.repo_paths import AGENT2
from app.harness.subprocess_runner import run_stage_subprocess

_RUNNERS_DIR = Path(__file__).resolve().parent.parent / "runners"


def invoke_agent2_candidate_search_round(
    *,
    agent1_view_path: str | Path,
    criteria_weights: dict[str, Any],
    search_policy: dict[str, Any],
    calibration_selection_policy: dict[str, Any],
    seed_modularization_id: str | None,
    submodel_module_id: str | None,
    calibration_evidence: list[dict[str, Any]] | None,
    calibration_runs_used_so_far: int,
    exclude_single_module_from_ranking: bool,
    apply_resolution_correction: bool,
    build_request_path: str | Path | None,
    correlation_id: str,
    run_id: str,
    stage_dir: str | Path,
    timeout_seconds: float = 300.0,
    functional_evaluation_selection_policy: dict[str, Any] | None = None,
    functional_evaluations_used_so_far: int = 0,
    functional_evaluation_evidence: list[dict[str, Any]] | None = None,
    attach_modularization: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run one real round-trip through Agent 2's own venv, and return the parsed
    ``serialize_round_result`` dict it writes. Raises ``RecursiveCandidateSearchError`` for a
    genuine infrastructure failure (a non-zero exit, a missing output file) -- never for a
    disclosed scientific outcome, which Agent 2's own round-runner always writes as data.
    """
    stage_dir = Path(stage_dir)
    stage_dir.mkdir(parents=True, exist_ok=True)
    output_path = stage_dir / f"candidate_search_round_{run_id}.json"

    args = [
        "--input",
        str(agent1_view_path),
        "--output",
        str(output_path),
        "--criteria-weights",
        json.dumps(criteria_weights),
        "--search-policy",
        json.dumps(search_policy),
        "--calibration-selection-policy",
        json.dumps(calibration_selection_policy),
        "--calibration-runs-used-so-far",
        str(calibration_runs_used_so_far),
        "--exclude-single-module-from-ranking",
        "true" if exclude_single_module_from_ranking else "false",
        "--correlation-id",
        correlation_id,
        "--run-id",
        run_id,
    ]
    if seed_modularization_id is not None:
        args += ["--seed-modularization-id", seed_modularization_id]
    if submodel_module_id is not None:
        args += ["--submodel-module-id", submodel_module_id]
    if build_request_path is not None:
        args += ["--build-request", str(build_request_path)]
    if apply_resolution_correction:
        args.append("--apply-resolution-correction")
    if calibration_evidence is not None:
        evidence_path = stage_dir / f"candidate_search_round_evidence_{run_id}.json"
        with open(evidence_path, "w") as f:
            json.dump(calibration_evidence, f)
        args += ["--calibration-evidence", str(evidence_path)]
    if functional_evaluation_selection_policy is not None:
        args += [
            "--functional-evaluation-selection-policy",
            json.dumps(functional_evaluation_selection_policy),
            "--functional-evaluations-used-so-far",
            str(functional_evaluations_used_so_far),
        ]
    if functional_evaluation_evidence is not None:
        functional_evidence_path = (
            stage_dir / f"candidate_search_round_functional_evidence_{run_id}.json"
        )
        with open(functional_evidence_path, "w") as f:
            json.dump(functional_evaluation_evidence, f)
        args += ["--functional-evaluation-evidence", str(functional_evidence_path)]
    if attach_modularization is not None:
        attach_path = stage_dir / f"candidate_search_round_attach_modularization_{run_id}.json"
        with open(attach_path, "w") as f:
            json.dump(attach_modularization, f)
        args += ["--attach-modularization", str(attach_path)]

    outcome = run_stage_subprocess(
        venv_python=AGENT2.venv_python,
        script_path=_RUNNERS_DIR / "run_agent2_candidate_search_round.py",
        cwd=AGENT2.repo_dir,
        args=args,
        timeout_seconds=timeout_seconds,
    )
    if outcome.returncode != 0 or not output_path.is_file():
        raise RecursiveCandidateSearchError(
            f"Agent 2 candidate-search-round subprocess failed for run_id={run_id!r} "
            f"(returncode={outcome.returncode}, timed_out={outcome.timed_out}): "
            f"{outcome.stderr[-500:]!r} -- this is an infrastructure/numerical failure, never "
            "genuine evidence about any candidate"
        )
    with open(output_path) as f:
        return json.load(f)


__all__ = ["invoke_agent2_candidate_search_round"]
