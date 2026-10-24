"""Tests for the Workbench <-> Harness whole-model Antimony-import fidelity-audit contract
(Whole-Model Antimony Import increment) and its canonical entrypoint
(``scripts/run_workbench_model_antimony_import_request.py``).

Mirrors ``tests/harness/test_workbench_model_antimony_verification_contract.py``'s own
established convention: real, end-to-end subprocess invocations (one real Agent 2 round, via
its own ``antimony``/``libsbml`` dependencies) rather than a mocked importer. This contract
takes Antimony text directly -- Agent 1 is never invoked here, so a short, literal,
hand-written Antimony string is real and sufficient for every test in this file.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from app.harness.workbench_contracts import (
    WORKBENCH_MODEL_ANTIMONY_IMPORT_CONTRACT_VERSION,
    WorkbenchModelAntimonyImportRequest,
    WorkbenchModelAntimonyImportResult,
    WorkbenchRunErrorCode,
    WorkbenchRunStatus,
    model_antimony_import_request_from_dict,
    model_antimony_import_request_to_dict,
    model_antimony_import_result_from_dict,
    model_antimony_import_result_to_dict,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_ENTRYPOINT = _REPO_ROOT / "scripts" / "run_workbench_model_antimony_import_request.py"

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

#: Exercises an assignment rule and an event, for the rule/event-count audit fields.
_VALID_ANTIMONY_TEXT_WITH_RULE_AND_EVENT = """
model test_model_rule_event
  compartment C1
  C1 = 1.0
  species S1 in C1
  species S2 in C1
  S1 = 10
  S2 = 0
  R1: S1 -> S2; k1*S1
  k1 = 0.1
  total := S1 + S2
  at (time > 5): S1 = 20
end
"""

#: A top-level statement before the model block -- the fixed silent-data-loss bug (Agent 2's
#: own ``getMainModuleName()`` used to pick its own implicit, empty module here instead).
_ANTIMONY_TEXT_WITH_TOP_LEVEL_STATEMENT = """
k_global = 5;
model probe
  compartment outer = 2.0;
  species A in outer = 10.0;
  species B in outer = 0.0;
  R1: A -> B; k_global * A;
end
"""

#: Two named models in one file -- ambiguous, never silently resolved to either one.
_ANTIMONY_TEXT_WITH_TWO_MODELS = """
model probe
  compartment outer = 2.0;
  species A in outer = 10.0;
end
model other
  compartment outer2 = 1.0;
  species C in outer2 = 1.0;
end
"""

_ANTIMONY_TEXT_WITH_FUNCTION_DEFINITION = """
function double(x)
  x * 2
end

model has_function
  compartment C1
  C1 = 1.0
  species S1 in C1
  S1 = 10
  R1: S1 -> ; double(0.1) * S1
end
"""


def _base_request(run_id: str, *, antimony_text: str, **overrides) -> dict:
    data = {
        "contract_version": WORKBENCH_MODEL_ANTIMONY_IMPORT_CONTRACT_VERSION,
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
    request = WorkbenchModelAntimonyImportRequest(
        contract_version=WORKBENCH_MODEL_ANTIMONY_IMPORT_CONTRACT_VERSION,
        run_id="roundtrip-test",
        antimony_text=_VALID_ANTIMONY_TEXT,
        correlation_id="corr-1",
        submitted_at="2026-01-01T00:00:00+00:00",
    )
    restored = model_antimony_import_request_from_dict(
        model_antimony_import_request_to_dict(request)
    )
    assert restored == request


def test_result_round_trips_through_dict():
    result = WorkbenchModelAntimonyImportResult(
        contract_version=WORKBENCH_MODEL_ANTIMONY_IMPORT_CONTRACT_VERSION,
        run_id="result-roundtrip",
        status=WorkbenchRunStatus.SUCCEEDED,
        import_succeeded=True,
        import_error_kind=None,
        import_message=None,
        compartment_ids=("C1",),
        compartment_names={"C1": "C1"},
        species_ids=("S1", "S2"),
        species_compartment_ids={"S1": "C1", "S2": "C1"},
        parameter_ids=("k1",),
        reaction_ids=("R1",),
        assignment_rule_count=0,
        rate_rule_count=0,
        algebraic_rule_count=0,
        event_count=0,
        antimony_import_parser_version="antimony-import-v2",
        started_at="2026-01-01T00:00:00+00:00",
        completed_at="2026-01-01T00:00:05+00:00",
        error=None,
        summary="imported",
    )
    restored = model_antimony_import_result_from_dict(
        model_antimony_import_result_to_dict(result)
    )
    assert restored == result


# --- Pre-execution rejections (fast, no subprocess) -----------------------------------------


def test_contract_version_mismatch_is_rejected(tmp_path):
    run_id = "antimony-import-version-mismatch"
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
                "contract_version": WORKBENCH_MODEL_ANTIMONY_IMPORT_CONTRACT_VERSION,
                "run_id": "antimony-import-missing-field",
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
        _cleanup_run_artifacts("antimony-import-missing-field")


# --- Real, end-to-end subprocess invocation (real Agent 2 antimony/libsbml import) -----------


def test_a_valid_model_imports_and_reports_real_structural_identifiers(tmp_path):
    run_id = "antimony-import-valid"
    try:
        request_data = _base_request(run_id, antimony_text=_VALID_ANTIMONY_TEXT)
        returncode, result = _invoke(tmp_path, request_data)
        assert returncode == 0, f"canonical entrypoint failed: {result}"
        assert result["status"] == WorkbenchRunStatus.SUCCEEDED.value
        assert result["import_succeeded"] is True
        assert sorted(result["species_ids"]) == ["S1", "S2"]
        assert result["compartment_ids"] == ["C1"]
        assert result["compartment_names"] == {"C1": "C1"}
        assert result["species_compartment_ids"] == {"S1": "C1", "S2": "C1"}
        assert result["parameter_ids"] == ["k1"]
        assert result["reaction_ids"] == ["R1"]
        assert result["antimony_import_parser_version"] is not None
    finally:
        _cleanup_run_artifacts(run_id)


def test_rule_and_event_counts_are_reported(tmp_path):
    run_id = "antimony-import-rule-event"
    try:
        request_data = _base_request(
            run_id, antimony_text=_VALID_ANTIMONY_TEXT_WITH_RULE_AND_EVENT
        )
        returncode, result = _invoke(tmp_path, request_data)
        assert returncode == 0, f"canonical entrypoint failed: {result}"
        assert result["import_succeeded"] is True
        assert result["assignment_rule_count"] == 1
        assert result["rate_rule_count"] == 0
        assert result["algebraic_rule_count"] == 0
        assert result["event_count"] == 1
    finally:
        _cleanup_run_artifacts(run_id)


def test_a_top_level_statement_before_the_model_does_not_lose_the_model(tmp_path):
    """Regression for the fixed Agent 2 silent-data-loss bug: previously, this exact input
    would import as an almost-entirely-empty model with no error. Confirmed fixed here at the
    full contract/subprocess level, not just inside Agent 2's own unit tests."""
    run_id = "antimony-import-top-level-statement"
    try:
        request_data = _base_request(
            run_id, antimony_text=_ANTIMONY_TEXT_WITH_TOP_LEVEL_STATEMENT
        )
        returncode, result = _invoke(tmp_path, request_data)
        assert returncode == 0, f"canonical entrypoint failed: {result}"
        assert result["import_succeeded"] is True
        assert result["compartment_ids"] == ["outer"]
        assert sorted(result["species_ids"]) == ["A", "B"]
    finally:
        _cleanup_run_artifacts(run_id)


def test_two_named_models_in_one_file_are_rejected_as_ambiguous(tmp_path):
    run_id = "antimony-import-two-models"
    try:
        request_data = _base_request(run_id, antimony_text=_ANTIMONY_TEXT_WITH_TWO_MODELS)
        returncode, result = _invoke(tmp_path, request_data)
        assert returncode == 0, f"canonical entrypoint failed: {result}"
        assert result["status"] == WorkbenchRunStatus.SUCCEEDED.value
        assert result["import_succeeded"] is False
        assert result["import_error_kind"] == "AMBIGUOUS_MODULE"
        assert "probe" in result["import_message"] and "other" in result["import_message"]
    finally:
        _cleanup_run_artifacts(run_id)


def test_a_function_definition_is_a_disclosed_unsupported_construct_not_an_infra_failure(
    tmp_path,
):
    run_id = "antimony-import-function-definition"
    try:
        request_data = _base_request(
            run_id, antimony_text=_ANTIMONY_TEXT_WITH_FUNCTION_DEFINITION
        )
        returncode, result = _invoke(tmp_path, request_data)
        assert returncode == 0, f"canonical entrypoint failed: {result}"
        assert result["status"] == WorkbenchRunStatus.SUCCEEDED.value
        assert result["import_succeeded"] is False
        assert result["import_error_kind"] == "UNSUPPORTED_CONSTRUCT"
        assert "function" in result["import_message"].lower()
    finally:
        _cleanup_run_artifacts(run_id)


def test_malformed_antimony_text_reports_import_failed_not_an_infrastructure_error(tmp_path):
    run_id = "antimony-import-malformed"
    try:
        request_data = _base_request(
            run_id, antimony_text="this is not valid antimony syntax at all !!!"
        )
        returncode, result = _invoke(tmp_path, request_data)
        assert returncode == 0, f"canonical entrypoint failed: {result}"
        assert result["status"] == WorkbenchRunStatus.SUCCEEDED.value
        assert result["import_succeeded"] is False
        assert result["import_error_kind"] == "MALFORMED"
    finally:
        _cleanup_run_artifacts(run_id)


def test_a_second_call_with_the_identical_run_id_replays_rather_than_reimporting(tmp_path):
    run_id = "antimony-import-replay"
    try:
        request_data = _base_request(run_id, antimony_text=_VALID_ANTIMONY_TEXT)
        first_returncode, first_result = _invoke(tmp_path, request_data)
        assert first_returncode == 0
        assert first_result["replayed"] is False

        second_returncode, second_result = _invoke(tmp_path, request_data)
        assert second_returncode == 0
        assert second_result["replayed"] is True
        assert second_result["species_ids"] == first_result["species_ids"]
    finally:
        _cleanup_run_artifacts(run_id)
