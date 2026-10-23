"""Tests for the Workbench <-> Harness model-antimony-verification contract (Model-Species
Catalog Prerequisite increment) and its canonical entrypoint
(``scripts/run_workbench_model_antimony_verification_request.py``).

Mirrors ``tests/harness/test_workbench_module_set_simulation_contract.py``'s own established
convention: real, end-to-end subprocess invocations (one real Agent 3 round, via its own
``antimony``/``roadrunner`` dependencies) rather than a mocked loader.

This contract takes Antimony text directly (never an Agent 1/2 input) -- Agent 2 is never
invoked here, so a short, literal, hand-written Antimony string is real and sufficient for
every test in this file; §9 of ``docs/26_model_species_catalog_prerequisite_increment.md``
covers the separate, genuinely-full-pipeline (real Agent 2 build -> this verification)
end-to-end proof.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from app.harness.workbench_contracts import (
    WORKBENCH_MODEL_ANTIMONY_VERIFICATION_CONTRACT_VERSION,
    WorkbenchModelAntimonyVerificationRequest,
    WorkbenchModelAntimonyVerificationResult,
    WorkbenchRunErrorCode,
    WorkbenchRunStatus,
    model_antimony_verification_request_from_dict,
    model_antimony_verification_request_to_dict,
    model_antimony_verification_result_from_dict,
    model_antimony_verification_result_to_dict,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_ENTRYPOINT = _REPO_ROOT / "scripts" / "run_workbench_model_antimony_verification_request.py"

_VALID_ANTIMONY_TEXT = """
model test_model
  compartment C1
  C1 = 1.0
  species S1 in C1
  species S2 in C1
  S1 = 10
  S2 = 0
  R1: S1 -> S2; k1*S1
  k1 = 0.1
end
"""

_VALID_ANTIMONY_TEXT_WITH_BOUNDARY_SPECIES = """
model test_model_boundary
  compartment C1
  C1 = 1.0
  species S1 in C1
  species S2 in C1
  const species S2
  S1 = 10
  S2 = 0
  R1: S1 -> S2; k1*S1
  k1 = 0.1
end
"""

#: Joint Calibration Workflow prerequisite increment (Workbench docs/31): one independent,
#: genuinely settable parameter (``k1``) and one assignment-rule-derived parameter (``Vmax``,
#: defined entirely in terms of ``k1`` -- never independently settable).
_VALID_ANTIMONY_TEXT_WITH_DERIVED_PARAMETER = """
model test_model_derived_parameter
  compartment C1
  C1 = 1.0
  species S1 in C1
  species S2 in C1
  S1 = 10
  S2 = 0
  R1: S1 -> S2; Vmax*S1
  k1 = 0.5
  Vmax := k1 * 2
end
"""


def _base_request(run_id: str, *, antimony_text: str, **overrides) -> dict:
    data = {
        "contract_version": WORKBENCH_MODEL_ANTIMONY_VERIFICATION_CONTRACT_VERSION,
        "run_id": run_id,
        "antimony_text": antimony_text,
    }
    data.update(overrides)
    return data


def _invoke(tmp_path: Path, request_data: dict) -> tuple[int, dict]:
    request_path = tmp_path / "request.json"
    output_path = tmp_path / "result.json"
    request_path.write_text(json.dumps(request_data))
    proc = subprocess.run(
        [
            sys.executable,
            str(_ENTRYPOINT),
            "--request",
            str(request_path),
            "--output",
            str(output_path),
        ],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=300,
    )
    result_data = json.loads(output_path.read_text()) if output_path.is_file() else None
    return proc.returncode, result_data


def _cleanup_run_artifacts(run_id: str) -> None:
    run_dir = _REPO_ROOT / "artifacts" / "runs" / run_id
    if run_dir.is_dir():
        shutil.rmtree(run_dir)


# --- Contract serialization/deserialization ------------------------------------------------


def test_request_round_trips_through_dict():
    request = WorkbenchModelAntimonyVerificationRequest(
        contract_version=WORKBENCH_MODEL_ANTIMONY_VERIFICATION_CONTRACT_VERSION,
        run_id="roundtrip-test",
        antimony_text=_VALID_ANTIMONY_TEXT,
        correlation_id="corr-1",
        submitted_at="2026-01-01T00:00:00+00:00",
    )
    restored = model_antimony_verification_request_from_dict(
        model_antimony_verification_request_to_dict(request)
    )
    assert restored == request


def test_result_round_trips_through_dict():
    result = WorkbenchModelAntimonyVerificationResult(
        contract_version=WORKBENCH_MODEL_ANTIMONY_VERIFICATION_CONTRACT_VERSION,
        run_id="result-roundtrip",
        status=WorkbenchRunStatus.SUCCEEDED,
        load_succeeded=True,
        load_message=None,
        floating_species_ids=("S1", "S2"),
        boundary_species_ids=(),
        compartment_ids=("C1",),
        antimony_version="3.2.0",
        roadrunner_version="2.10.0",
        started_at="2026-01-01T00:00:00+00:00",
        completed_at="2026-01-01T00:00:05+00:00",
        error=None,
        summary="verified",
    )
    restored = model_antimony_verification_result_from_dict(
        model_antimony_verification_result_to_dict(result)
    )
    assert restored == result


# --- Pre-execution rejections (fast, no subprocess) -----------------------------------------


def test_contract_version_mismatch_is_rejected(tmp_path):
    run_id = "antimony-verify-version-mismatch"
    try:
        request_data = _base_request(
            run_id, antimony_text=_VALID_ANTIMONY_TEXT, contract_version="not-real"
        )
        returncode, result = _invoke(tmp_path, request_data)
        assert returncode == 1
        assert result["error"]["code"] == WorkbenchRunErrorCode.CONTRACT_VERSION_MISMATCH.value
    finally:
        _cleanup_run_artifacts(run_id)


def test_malformed_request_missing_antimony_text_is_rejected(tmp_path):
    request_path = tmp_path / "request.json"
    output_path = tmp_path / "result.json"
    request_path.write_text(
        json.dumps(
            {
                "contract_version": WORKBENCH_MODEL_ANTIMONY_VERIFICATION_CONTRACT_VERSION,
                "run_id": "antimony-verify-missing-field",
            }
        )
    )
    proc = subprocess.run(
        [
            sys.executable,
            str(_ENTRYPOINT),
            "--request",
            str(request_path),
            "--output",
            str(output_path),
        ],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    try:
        assert proc.returncode == 1
        result = json.loads(output_path.read_text())
        assert result["error"]["code"] == WorkbenchRunErrorCode.MALFORMED_REQUEST.value
    finally:
        _cleanup_run_artifacts("antimony-verify-missing-field")


# --- Real, end-to-end subprocess invocation (real Agent 3 antimony/roadrunner load) ---------


def test_a_valid_model_loads_and_reports_real_floating_species(tmp_path):
    run_id = "antimony-verify-valid-floating"
    try:
        request_data = _base_request(run_id, antimony_text=_VALID_ANTIMONY_TEXT)
        returncode, result = _invoke(tmp_path, request_data)
        assert returncode == 0, f"canonical entrypoint failed: {result}"
        assert result["status"] == WorkbenchRunStatus.SUCCEEDED.value
        assert result["load_succeeded"] is True
        assert sorted(result["floating_species_ids"]) == ["S1", "S2"]
        assert result["boundary_species_ids"] == []
        assert result["compartment_ids"] == ["C1"]
    finally:
        _cleanup_run_artifacts(run_id)


def test_a_boundary_species_is_reported_separately_from_floating(tmp_path):
    """The exact distinction a species catalog must get right: a real, compiled boundary
    species is a genuine, addressable species -- never silently absent, never conflated with a
    floating one."""
    run_id = "antimony-verify-boundary"
    try:
        request_data = _base_request(
            run_id, antimony_text=_VALID_ANTIMONY_TEXT_WITH_BOUNDARY_SPECIES
        )
        returncode, result = _invoke(tmp_path, request_data)
        assert returncode == 0, f"canonical entrypoint failed: {result}"
        assert result["floating_species_ids"] == ["S1"]
        assert result["boundary_species_ids"] == ["S2"]
    finally:
        _cleanup_run_artifacts(run_id)


def test_an_independent_parameter_is_distinguished_from_an_assignment_rule_derived_one(tmp_path):
    """The exact distinction a parameter catalog must get right: ``k1`` is reported as a real,
    independently settable global parameter; ``Vmax`` (entirely computed from ``k1`` by an
    assignment rule) is reported too, but also named in
    ``assignment_rule_derived_parameter_ids`` -- never presented as if it were equally
    independent/fittable."""
    run_id = "antimony-verify-derived-parameter"
    try:
        request_data = _base_request(
            run_id, antimony_text=_VALID_ANTIMONY_TEXT_WITH_DERIVED_PARAMETER
        )
        returncode, result = _invoke(tmp_path, request_data)
        assert returncode == 0, f"canonical entrypoint failed: {result}"
        assert result["load_succeeded"] is True
        assert set(result["global_parameter_ids"]) == {"k1", "Vmax"}
        assert result["assignment_rule_derived_parameter_ids"] == ["Vmax"]
    finally:
        _cleanup_run_artifacts(run_id)


def test_malformed_antimony_text_reports_load_failed_not_an_infrastructure_error(tmp_path):
    """A compilation failure is a real, reported outcome (``status=SUCCEEDED``,
    ``load_succeeded=False``) -- never ``WorkbenchRunStatus.FAILED``, which is reserved for a
    genuine infrastructure defect this workflow itself never caused."""
    run_id = "antimony-verify-malformed-antimony"
    try:
        request_data = _base_request(
            run_id, antimony_text="this is not valid antimony syntax at all !!!"
        )
        returncode, result = _invoke(tmp_path, request_data)
        assert returncode == 0, f"canonical entrypoint failed: {result}"
        assert result["status"] == WorkbenchRunStatus.SUCCEEDED.value
        assert result["load_succeeded"] is False
        assert result["load_message"] is not None
        assert result["floating_species_ids"] == []
    finally:
        _cleanup_run_artifacts(run_id)


def test_a_second_call_with_the_identical_run_id_replays_rather_than_reloading(tmp_path):
    run_id = "antimony-verify-replay"
    try:
        request_data = _base_request(run_id, antimony_text=_VALID_ANTIMONY_TEXT)
        first_returncode, first_result = _invoke(tmp_path, request_data)
        assert first_returncode == 0
        assert first_result["replayed"] is False

        second_returncode, second_result = _invoke(tmp_path, request_data)
        assert second_returncode == 0
        assert second_result["replayed"] is True
        assert second_result["floating_species_ids"] == first_result["floating_species_ids"]
    finally:
        _cleanup_run_artifacts(run_id)
