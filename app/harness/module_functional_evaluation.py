"""Functional Modularity Criteria from Agents 3 and 4: routes one Agent 2 candidate module's
own functional-evaluation request -- a battery of deterministic perturbations spanning both
inside and outside that module, against the *whole* canonical network (never the module's own
filtered standalone artifact: dynamic isolation/sensitivity coherence are properties of how a
module behaves *relative to its surrounding context*, which only exists in the whole-network
simulation) -- through Agent 3, and maps the result back into a structured
``ModuleFunctionalEvaluationResult`` dict for Agent 2's own ``app.agent2.module_evaluation
.functional_adapter`` to parse.

**Agent 2 never calls Agent 3 directly** -- this module is the one, explicit routing point,
mirroring ``app.harness.module_calibration``'s own identical role for Agent 4. It never imports
Agent 2's or Agent 3's own Python package -- only the documented plain-dict shapes are shared.

Reuses Agent 3's own, already-existing, unchanged ``app.agent3.pipeline.run_agent3_pipeline``
(which already accepts an explicit ``perturbation_specs`` override) via a new, focused runner
script (``run_agent3_functional_evaluation.py``) -- no new Agent 3 simulation algorithm.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.harness.repo_paths import AGENT3
from app.harness.subprocess_runner import run_stage_subprocess
from app.harness.version import FUNCTIONAL_EVALUATION_WORKFLOW_POLICY_VERSION

_RUNNERS_DIR = Path(__file__).resolve().parent / "runners"

#: Agent 3's own ``SimulationStatus`` values meaning the whole-network model could not even be
#: loaded/simulated at all -- distinct from any one perturbation's own, individually-disclosed
#: ``simulation_status`` (a module can still be scored from the perturbations that *did*
#: succeed even when others failed; only a wholesale load failure makes the entire analysis
#: unsupported).
_UNSUPPORTED_OVERALL_STATUSES = frozenset({"MODEL_LOAD_FAILED"})


class ModuleFunctionalEvaluationWorkflowError(ValueError):
    """Raised only for a genuine orchestration/infrastructure defect -- a malformed request
    dict, or an Agent 3 subprocess crash or timeout -- never for a real, disclosed simulation
    outcome (which Agent 3 itself always reports as data, per ``SimulationStatus``). Never
    persisted as a cached result: a retry after the underlying problem is fixed must be free to
    actually re-run, never replay a stale infrastructure failure."""


def build_agent3_functional_evaluation_input(request: dict[str, Any]) -> dict[str, Any]:
    """One ``ModuleFunctionalEvaluationRequest`` dict -> the input
    ``run_agent3_functional_evaluation.py`` consumes unchanged: the whole-network handoff,
    the baseline simulation configuration, and the perturbation target battery (stripped of
    Agent 2's own ``is_internal`` tag, which Agent 3 never needs -- it stays module-agnostic,
    perturbing only what it is told to perturb)."""
    return {
        "agent2_model": dict(request["whole_network_handoff"]),
        "baseline_request": dict(request["baseline_request"]),
        "perturbation_specs": [
            {
                "target_kind": t["target_kind"],
                "target_id": t["target_id"],
                "fraction": float(t["fraction"]),
            }
            for t in request["perturbation_targets"]
        ],
    }


def map_functional_result_to_module_evaluation(
    request: dict[str, Any], agent3_report: dict[str, Any], *, evaluation_id: str
) -> dict[str, Any]:
    """Agent 3's own ``Agent3Report`` dict -> one ``ModuleFunctionalEvaluationResult`` dict.

    Matches each requested target to its own perturbation result *positionally* --
    ``run_perturbation_smoke_tests`` is already documented and tested
    (``test_run_perturbation_smoke_tests_preserves_spec_order``) to preserve spec order
    exactly, so this never needs to re-resolve targets by name. Raises ``ModuleFunctional
    EvaluationWorkflowError`` only if that invariant is somehow violated (a genuine wiring
    defect, never a disclosed outcome).
    """
    base: dict[str, Any] = {
        "evaluation_id": evaluation_id,
        "request_id": request["request_id"],
        "correlation_id": request["correlation_id"],
        "run_id": request["run_id"],
        "parent_model_id": request["parent_model_id"],
        "modularization_id": request["modularization_id"],
        "module_id": request["module_id"],
        "policy_version": FUNCTIONAL_EVALUATION_WORKFLOW_POLICY_VERSION,
        "warnings": [],
        "provenance_refs": [f"agent3-report::{agent3_report['report_id']}"],
    }

    perturbations = agent3_report.get("perturbations", [])
    targets = request["perturbation_targets"]
    if agent3_report["overall_status"] in _UNSUPPORTED_OVERALL_STATUSES or not perturbations:
        base["status"] = "UNSUPPORTED_ANALYSIS"
        base["perturbation_effects"] = []
        base["warnings"] = [
            f"whole-network simulation overall_status={agent3_report['overall_status']!r} -- "
            "no perturbation could be meaningfully run"
        ]
        return base

    if len(perturbations) != len(targets):
        raise ModuleFunctionalEvaluationWorkflowError(
            f"Agent 3 returned {len(perturbations)} perturbation results for "
            f"{len(targets)} requested targets -- order/count mismatch, a genuine wiring "
            "defect, never a disclosed outcome"
        )

    effects = []
    for target, perturbation in zip(targets, perturbations, strict=True):
        spec = perturbation["spec"]
        if spec["target_kind"] != target["target_kind"] or spec["target_id"] != target["target_id"]:
            raise ModuleFunctionalEvaluationWorkflowError(
                f"perturbation result {spec!r} does not match requested target {target!r} at "
                "the same position -- a genuine wiring defect, never a disclosed outcome"
            )
        effects.append(
            {
                "target_kind": target["target_kind"],
                "target_id": target["target_id"],
                "is_internal": target["is_internal"],
                "simulation_status": perturbation["simulation_status"],
                "remained_numerically_stable": perturbation["remained_numerically_stable"],
                "relative_change_by_species": dict(
                    perturbation.get("relative_change_by_species") or {}
                ),
            }
        )

    base["status"] = "EVALUATED"
    base["perturbation_effects"] = effects
    return base


def run_module_functional_evaluation_workflow(
    request: dict[str, Any], *, stage_dir: str | Path, timeout_seconds: float = 300.0
) -> dict[str, Any]:
    """Route ``request`` (a ``ModuleFunctionalEvaluationRequest`` dict) through Agent 3, and
    return one ``ModuleFunctionalEvaluationResult`` dict.

    **Persistence/replay**: the result is written to ``<stage_dir>/functional_evaluation_result_
    <run_id>.json``; a second call with the identical ``run_id`` reads that file back verbatim
    rather than re-invoking Agent 3 -- mirrors ``run_module_calibration_workflow``'s own
    established replay pattern exactly.

    Never calls Agent 3 from inside Agent 2's own process -- this function is the one, explicit
    routing point, exactly like ``run_module_calibration_workflow`` already is for Agent 4.
    """
    stage_dir = Path(stage_dir)
    stage_dir.mkdir(parents=True, exist_ok=True)
    run_id = request["run_id"]
    result_path = stage_dir / f"functional_evaluation_result_{run_id}.json"
    if result_path.is_file():
        with open(result_path) as f:
            return json.load(f)

    agent3_input = build_agent3_functional_evaluation_input(request)
    agent3_input_path = stage_dir / f"functional_evaluation_agent3_input_{run_id}.json"
    with open(agent3_input_path, "w") as f:
        json.dump(agent3_input, f, indent=2)
    agent3_output_path = stage_dir / f"functional_evaluation_agent3_output_{run_id}.json"
    outcome = run_stage_subprocess(
        venv_python=AGENT3.venv_python,
        script_path=_RUNNERS_DIR / "run_agent3_functional_evaluation.py",
        cwd=AGENT3.repo_dir,
        args=["--input", str(agent3_input_path), "--output", str(agent3_output_path)],
        timeout_seconds=timeout_seconds,
    )
    if outcome.returncode != 0 or not agent3_output_path.is_file():
        # Identical reasoning as app.harness.module_calibration's own Agent 3 branch: a
        # non-zero exit means something actually broke (a bug, a missing dependency, a
        # timeout), never real evidence that this module itself is poorly isolated/incoherent.
        # Never persisted as a cached outcome -- a retry after fixing the underlying
        # infrastructure problem must be free to actually re-run.
        raise ModuleFunctionalEvaluationWorkflowError(
            f"Agent 3 subprocess failed for run_id={run_id!r} (returncode="
            f"{outcome.returncode}, timed_out={outcome.timed_out}): "
            f"{outcome.stderr[-500:]!r} -- this is an infrastructure/numerical failure, "
            "never genuine evidence about the proposed module"
        )
    with open(agent3_output_path) as f:
        agent3_report = json.load(f)

    result = map_functional_result_to_module_evaluation(
        request, agent3_report, evaluation_id=f"functional-evaluation::{run_id}"
    )
    with open(result_path, "w") as f:
        json.dump(result, f, indent=2)
    return result


__all__ = [
    "ModuleFunctionalEvaluationWorkflowError",
    "build_agent3_functional_evaluation_input",
    "map_functional_result_to_module_evaluation",
    "run_module_functional_evaluation_workflow",
]
