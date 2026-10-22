"""Model-Species Catalog Prerequisite increment: verify a whole model's own Antimony text
actually compiles, and report its real, loaded species/compartment identifiers -- the one,
explicit routing point into Agent 3's own loader, mirroring every other single-stage
``app.harness.module_*`` workflow's identical role and structure.

Deliberately minimal: cross-referencing these real identifiers against Agent 2's own structural
``FullNetwork``/``antimony_symbol_map`` (to attach canonical species ids, compartment context,
and disclose any species that did not survive into the compiled model) is the Workbench's own
responsibility, not this module's -- this module answers exactly one question ("does this
Antimony text load, and what are its real identifiers"), never anything about what a species
*should* be called or where it structurally came from.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.harness.repo_paths import AGENT3
from app.harness.subprocess_runner import run_stage_subprocess
from app.harness.version import MODEL_ANTIMONY_VERIFICATION_WORKFLOW_POLICY_VERSION

_RUNNERS_DIR = Path(__file__).resolve().parent / "runners"


class ModelAntimonyVerificationWorkflowError(ValueError):
    """Raised only for a genuine orchestration/infrastructure defect -- an Agent 3 subprocess
    crash, timeout, or malformed output -- never for an Antimony compilation failure itself
    (that is a normal, reported outcome: ``load_succeeded: false``). Never persisted as a
    cached result: a retry after the underlying problem is fixed must be free to actually
    re-run.
    """


def run_model_antimony_verification_workflow(
    request: dict[str, Any], *, stage_dir: str | Path, timeout_seconds: float = 300.0
) -> dict[str, Any]:
    """Route ``request["antimony_text"]`` through Agent 3's own loader and return
    ``{"load_succeeded", "load_message", "floating_species_ids", "boundary_species_ids",
    "compartment_ids", "antimony_version", "roadrunner_version"}``.

    ``request`` keys: ``run_id``, ``antimony_text`` (the real, already-generated Antimony
    source for one whole model -- never a module's own reduced/standalone text, which has its
    own, different, already-established simulation path).

    **Persistence/replay**: the result is written to ``<stage_dir>/model_antimony_verification_
    result_<run_id>.json``; a second call with the identical ``run_id`` reads that file back
    verbatim rather than re-invoking Agent 3 -- mirrors every other workflow's own established
    replay pattern exactly.
    """
    stage_dir = Path(stage_dir)
    stage_dir.mkdir(parents=True, exist_ok=True)
    run_id = request["run_id"]
    result_path = stage_dir / f"model_antimony_verification_result_{run_id}.json"
    if result_path.is_file():
        with open(result_path) as f:
            return json.load(f)

    antimony_text_path = stage_dir / f"model_antimony_verification_input_{run_id}.txt"
    antimony_text_path.write_text(request["antimony_text"])

    output_path = stage_dir / f"model_antimony_verification_output_{run_id}.json"
    outcome = run_stage_subprocess(
        venv_python=AGENT3.venv_python,
        script_path=_RUNNERS_DIR / "run_agent3_inspect_antimony_model.py",
        cwd=AGENT3.repo_dir,
        args=["--input", str(antimony_text_path), "--output", str(output_path)],
        timeout_seconds=timeout_seconds,
    )
    if outcome.returncode != 0 or not output_path.is_file():
        raise ModelAntimonyVerificationWorkflowError(
            f"Agent 3 Antimony-inspection subprocess failed for run_id={run_id!r} (returncode="
            f"{outcome.returncode}, timed_out={outcome.timed_out}): {outcome.stderr[-500:]!r} "
            "-- this is an infrastructure failure, never evidence about the model itself"
        )
    with open(output_path) as f:
        inspection = json.load(f)

    result = {
        "run_id": run_id,
        "load_succeeded": inspection["load_succeeded"],
        "load_message": inspection["load_message"],
        "floating_species_ids": inspection["floating_species_ids"],
        "boundary_species_ids": inspection["boundary_species_ids"],
        "compartment_ids": inspection["compartment_ids"],
        "antimony_version": inspection["antimony_version"],
        "roadrunner_version": inspection["roadrunner_version"],
        "policy_version": MODEL_ANTIMONY_VERIFICATION_WORKFLOW_POLICY_VERSION,
    }
    with open(result_path, "w") as f:
        json.dump(result, f, indent=2)
    return result


__all__ = [
    "MODEL_ANTIMONY_VERIFICATION_WORKFLOW_POLICY_VERSION",
    "ModelAntimonyVerificationWorkflowError",
    "run_model_antimony_verification_workflow",
]
