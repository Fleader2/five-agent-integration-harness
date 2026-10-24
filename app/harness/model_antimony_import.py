"""Whole-Model Antimony Import increment: audit import fidelity (rule/event counts, which
construct -- if any -- was rejected and why) for caller-supplied Antimony text through Agent
2's own, pre-existing, unmodified ``import_antimony`` -- the one, explicit routing point into
it, mirroring ``app.harness.model_antimony_verification``'s identical structure and role.

Deliberately audit-only, never a replacement for ``model_antimony_verification``: this
workflow never performs the real executability check or species/parameter/compartment catalog
capture -- that stays entirely with Agent 3's own loader, through the wholly separate,
unmodified ``model_antimony_verification`` contract, called independently against the
identical Antimony text. Nothing here ever re-serializes or substitutes Agent 2's own
canonical form for the Antimony text the caller originally supplied.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.harness.repo_paths import AGENT2
from app.harness.subprocess_runner import run_stage_subprocess
from app.harness.version import MODEL_ANTIMONY_IMPORT_WORKFLOW_POLICY_VERSION

_RUNNERS_DIR = Path(__file__).resolve().parent / "runners"


class ModelAntimonyImportWorkflowError(ValueError):
    """Raised only for a genuine orchestration/infrastructure defect -- an Agent 2 subprocess
    crash, timeout, or malformed output -- never for a disclosed import outcome (that is a
    normal, reported outcome: ``import_succeeded: false``). Never persisted as a cached
    result: a retry after the underlying problem is fixed must be free to actually re-run.
    """


def run_model_antimony_import_workflow(
    request: dict[str, Any], *, stage_dir: str | Path, timeout_seconds: float = 300.0
) -> dict[str, Any]:
    """Route ``request["antimony_text"]`` through Agent 2's own ``import_antimony`` and return
    ``{"import_succeeded", "import_error_kind", "import_message", "compartment_ids",
    "compartment_names", "species_ids", "species_compartment_ids", "parameter_ids",
    "reaction_ids", "assignment_rule_count", "rate_rule_count", "algebraic_rule_count",
    "event_count", "antimony_import_parser_version"}``.

    ``request`` keys: ``run_id``, ``antimony_text``.

    **Persistence/replay**: the result is written to ``<stage_dir>/model_antimony_import_
    result_<run_id>.json``; a second call with the identical ``run_id`` reads that file back
    verbatim rather than re-invoking Agent 2 -- mirrors every other workflow's own established
    replay pattern exactly.
    """
    stage_dir = Path(stage_dir)
    stage_dir.mkdir(parents=True, exist_ok=True)
    run_id = request["run_id"]
    result_path = stage_dir / f"model_antimony_import_result_{run_id}.json"
    if result_path.is_file():
        with open(result_path) as f:
            return json.load(f)

    input_path = stage_dir / f"model_antimony_import_input_{run_id}.json"
    input_path.write_text(json.dumps({"antimony_text": request["antimony_text"]}))

    output_path = stage_dir / f"model_antimony_import_output_{run_id}.json"
    outcome = run_stage_subprocess(
        venv_python=AGENT2.venv_python,
        script_path=_RUNNERS_DIR / "run_agent2_import_antimony.py",
        cwd=AGENT2.repo_dir,
        args=["--input", str(input_path), "--output", str(output_path)],
        timeout_seconds=timeout_seconds,
    )
    if outcome.returncode != 0 or not output_path.is_file():
        raise ModelAntimonyImportWorkflowError(
            f"Agent 2 Antimony-import subprocess failed for run_id={run_id!r} (returncode="
            f"{outcome.returncode}, timed_out={outcome.timed_out}): {outcome.stderr[-500:]!r} "
            "-- this is an infrastructure failure, never evidence about the model itself"
        )
    with open(output_path) as f:
        audit = json.load(f)

    result = {
        "run_id": run_id,
        "import_succeeded": audit["import_succeeded"],
        "import_error_kind": audit.get("import_error_kind"),
        "import_message": audit.get("import_message"),
        "compartment_ids": audit.get("compartment_ids", []),
        "compartment_names": audit.get("compartment_names", {}),
        "species_ids": audit.get("species_ids", []),
        "species_compartment_ids": audit.get("species_compartment_ids", {}),
        "parameter_ids": audit.get("parameter_ids", []),
        "reaction_ids": audit.get("reaction_ids", []),
        "assignment_rule_count": audit.get("assignment_rule_count", 0),
        "rate_rule_count": audit.get("rate_rule_count", 0),
        "algebraic_rule_count": audit.get("algebraic_rule_count", 0),
        "event_count": audit.get("event_count", 0),
        "antimony_import_parser_version": audit.get("antimony_import_parser_version"),
        "policy_version": MODEL_ANTIMONY_IMPORT_WORKFLOW_POLICY_VERSION,
    }
    with open(result_path, "w") as f:
        json.dump(result, f, indent=2)
    return result


__all__ = [
    "MODEL_ANTIMONY_IMPORT_WORKFLOW_POLICY_VERSION",
    "ModelAntimonyImportWorkflowError",
    "run_model_antimony_import_workflow",
]
