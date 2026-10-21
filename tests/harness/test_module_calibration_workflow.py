"""Tests for Recursive Module Evaluation Orchestration: ``app.harness.module_calibration``.

Two kinds of coverage:

* **Unit tests** (no subprocess, fast, deterministic) for ``map_calibration_result_to_module_
  evaluation``'s own status-mapping/field-derivation policy, against synthetic ``Agent4Report``
  dicts -- covers INSUFFICIENT_DATA/UNIDENTIFIABLE/CALIBRATION_FAILED/INVALID_REQUEST without
  needing a real optimizer run for every case.
* **One real, full round trip** (``test_full_round_trip_recovers_true_parameter``) -- an actual
  subprocess invocation of Agent 3's then Agent 4's own real pipelines against a genuine
  one-parameter exponential-decay module, confirming the whole wiring (request ->
  Agent2->Agent3 handoff -> Agent 3 subprocess -> Agent2/Agent3->Agent4 handoff -> Agent 4
  subprocess -> mapped result) actually works end to end, not just on paper. Ground-truth
  observations are precomputed analytically (``a(t) = a0 * exp(-k*t)``) with plain ``math.exp``
  -- no RoadRunner dependency inside this test process itself.
"""

from __future__ import annotations

import json
import math
import uuid

import pytest

from app.harness.module_calibration import (
    ModuleCalibrationWorkflowError,
    build_module_agent3_handoff,
    map_calibration_result_to_module_evaluation,
    run_module_calibration_workflow,
)
from app.harness.repo_paths import AGENT3, AGENT4, check_repo_available

pytestmark = pytest.mark.skipif(
    check_repo_available(AGENT3) is not None or check_repo_available(AGENT4) is not None,
    reason="Agent 3/Agent 4 sibling repos (with their own venvs) are not available",
)

# --- Fixtures --------------------------------------------------------------------------------

_TRUE_K = 0.7
_A0 = 10.0


def _module_handoff(*, initial_k_guess: str = "0.1") -> dict:
    antimony_text = f"""
    model decay
      compartment C = 1
      species a in C
      a = {_A0}
      r1: a -> ;
      r1 = k1 * a
      k1 = {initial_k_guess}
    end
    """
    return {
        "contract_version": "agent2-downstream-v3",
        "model_id": "parent-model::module::mz-1::mod-1",
        "network_id": "parent-model::module::mz-1::mod-1",
        "antimony_text": antimony_text,
        "antimony_generator_version": "antimony-generation-v7",
        "antimony_symbol_map": {
            "species": {"a": "a"},
            "reactions": {"r1": "r1"},
            "parameters": {"k1": "k1"},
        },
        "readiness": "EXECUTABLE",
        "unresolved_reaction_ids": [],
        "unresolved_kinetic_law_ids": [],
        "compartments": [
            {
                "compartment_id": "C",
                "name": "C",
                "initial_volume": "1",
                "volume_unit": None,
                "constant": True,
            }
        ],
        "species": [
            {
                "species_id": "a",
                "name": "a",
                "compartment_id": "C",
                "source_compound_id": None,
                "source_enzyme_state_id": None,
                "source_protein_id": None,
                "initial_amount": None,
                "initial_concentration": str(_A0),
                "constant": False,
                "boundary_condition": False,
                "initialization_source": None,
            }
        ],
        "reactions": [
            {
                "reaction_id": "r1",
                "name": "r1",
                "reversible": False,
                "participants": [{"species_id": "a", "role": "REACTANT", "stoichiometry": "1"}],
            }
        ],
        "kinetic_laws": [
            {
                "kinetic_law_id": "kl-r1",
                "reaction_id": "r1",
                "law_type": "MASS_ACTION",
                "expression": "k1 * a",
                "parameter_ids": ["k1"],
                "species_ids": ["a"],
                "enzyme_state_id": None,
                "protein_id": None,
                "complex_id": None,
                "rate_law_scope": "LUMPED_EFFECTIVE_RATE",
                "assumptions": [],
            }
        ],
        "parameters": [
            {
                "parameter_id": "k1",
                "name": "k1",
                "source": "HEURISTIC_INITIALIZATION",
                "value": initial_k_guess,
                "unit": None,
                "reaction_id": "r1",
                "kinetic_law_assignment_id": None,
                "uncertainty_text": None,
                "provenance_refs": [],
                "lower_bound": "0.001",
                "upper_bound": "5.0",
                "fixed": False,
            }
        ],
        "model_assumptions": [],
    }


def _request(*, run_id: str, module_handoff: dict | None = None) -> dict:
    return {
        "request_id": f"module-calibration-request::{run_id}",
        "correlation_id": f"corr::{run_id}",
        "run_id": run_id,
        "parent_model_id": "parent-model",
        "modularization_id": "mz-1",
        "module_id": "mod-1",
        "module_handoff": module_handoff if module_handoff is not None else _module_handoff(),
        "boundary_ports": [
            {
                "port_id": "port-1",
                "species_id": "a",
                "direction": "INPUT",
                "externally_controlled": True,
                "initial_value": str(_A0),
                "unit": None,
            }
        ],
        "calibration_dataset_references": [],
        "requested_at": None,
    }


def _true_observations() -> tuple[list[float], list[float]]:
    time_points = [1.0, 2.0, 4.0, 6.0, 9.0, 12.0, 16.0, 20.0]
    values = [_A0 * math.exp(-_TRUE_K * t) for t in time_points]
    return time_points, values


def _calibration_request() -> dict:
    time_points, values = _true_observations()
    return {
        "request_id": "calib-req-1",
        "targets": [
            {
                "target_kind": "PARAMETER",
                "target_id": "k1",
                "bounds": {"lower": 0.001, "upper": 5.0},
            }
        ],
        "observations": {
            "observation_set_id": "decay-train-set",
            "observations": [
                {
                    "observation_id": "obs-a",
                    "target_species_id": "a",
                    "kind": "TIME_SERIES",
                    "time_points": time_points,
                    "values": values,
                    "partition": "TRAIN",
                }
            ],
        },
    }


# --- Real, full round trip -------------------------------------------------------------------


def test_full_round_trip_recovers_true_parameter(tmp_path):
    run_id = f"module-calib-success-{uuid.uuid4().hex[:8]}"
    request = _request(run_id=run_id)
    result = run_module_calibration_workflow(request, _calibration_request(), stage_dir=tmp_path)
    assert result["status"] == "CALIBRATION_SUPPORTED"
    assert result["parent_model_id"] == "parent-model"
    assert result["modularization_id"] == "mz-1"
    assert result["module_id"] == "mod-1"
    assert result["fit_quality"]["objective_after"] < result["fit_quality"]["objective_before"]
    estimates = {p["target_id"]: p["fitted_value"] for p in result["parameter_uncertainty"]}
    assert estimates["k1"] == pytest.approx(_TRUE_K, rel=0.05)
    # Calibration Evidence Integration into Weight-Space Exploration increment: Agent 4 now
    # exposes a local standard-error estimate directly -- genuinely available here, never
    # fabricated as a placeholder.
    standard_errors = {p["target_id"]: p["standard_error"] for p in result["parameter_uncertainty"]}
    assert standard_errors["k1"] is not None
    assert standard_errors["k1"] >= 0
    # Only one target was fit -- no correlation pair exists to report.
    assert result["parameter_correlations"] == []


def test_persistence_replay_does_not_rerun_agents(tmp_path):
    run_id = f"module-calib-replay-{uuid.uuid4().hex[:8]}"
    request = _request(run_id=run_id)
    first = run_module_calibration_workflow(request, _calibration_request(), stage_dir=tmp_path)

    # Remove the intermediate artifacts a real re-run would need -- if replay actually
    # re-invoked either agent, this second call would fail outright (missing input files) or
    # produce a *second*, distinct run; it must instead return the identical cached result.
    for pattern in ("module_agent3_input_*", "module_agent3_output_*", "module_agent4_*"):
        for p in tmp_path.glob(f"{pattern}{run_id}.json"):
            p.unlink()

    second = run_module_calibration_workflow(request, _calibration_request(), stage_dir=tmp_path)
    assert second == first


def test_agent3_infrastructure_failure_raises_never_disclosed_as_evidence(tmp_path):
    """A malformed module_handoff (missing a required Agent2->Agent3 field) makes Agent 3's own
    run_agent3.py crash with a non-zero exit -- never Agent 3's own disclosed SIMULATION_FAILED
    status. This must surface as ModuleCalibrationWorkflowError, never a silently-fabricated
    CALIBRATION_FAILED (genuine negative evidence) result, and must never be persisted as a
    cached outcome."""
    run_id = f"module-calib-infra-fail-{uuid.uuid4().hex[:8]}"
    broken_handoff = dict(_module_handoff())
    del broken_handoff["contract_version"]
    request = _request(run_id=run_id, module_handoff=broken_handoff)
    with pytest.raises(ModuleCalibrationWorkflowError):
        run_module_calibration_workflow(request, _calibration_request(), stage_dir=tmp_path)
    assert not (tmp_path / f"module_calibration_result_{run_id}.json").is_file()


# --- Unit tests: status mapping (no subprocess) ----------------------------------------------


def _agent4_report(*, status: str, **calibration_overrides) -> dict:
    calibration = {
        "calibration_run_id": "run-1",
        "status": status,
        "objective_before": 10.0,
        "objective_after": 1.0,
        "parameter_estimates": [
            {
                "target_kind": "PARAMETER",
                "target_id": "k1",
                "original_value": 0.1,
                "original_source": "HEURISTIC_INITIALIZATION",
                "fitted_value": 0.7,
                "lower_bound": 0.001,
                "upper_bound": 5.0,
                "at_lower_bound": False,
                "at_upper_bound": False,
                "new_source": "CALIBRATED",
                "provenance_refs": [],
            }
        ],
        "residuals": [
            {
                "observation_id": "obs-a",
                "partition": "TRAIN",
                "residuals": [0.1, 0.2],
                "sum_squared_residual": 0.05,
                "weighted_sum_squared_residual": 0.05,
                "n_points": 2,
            }
        ],
        "identifiability_findings": [],
        "optimizer_message": None,
        "n_multistarts": 3,
        "best_start_index": 0,
        "all_start_objectives": [1.0, 1.1, 1.2],
    } | calibration_overrides
    return {
        "report_id": "agent4-report-1",
        "agent4_contract_version": "0.1",
        "agent2_model_id": "parent-model::module::mz-1::mod-1",
        "agent3_report_id": "agent3-report-1",
        "request_id": "req-1",
        "calibration": calibration,
        "fixed_parameters_verified_unchanged": True,
        "fixed_parameter_ids_checked": [],
        "sufficient_for_agent5": True,
        "sufficiency_note": "ok",
    }


_AGENT3_REPORT = {"report_id": "agent3-report-1"}
_REQUEST_DICT = _request(run_id="unit-test-run")


def test_map_success_to_calibration_supported():
    result = map_calibration_result_to_module_evaluation(
        _REQUEST_DICT,
        _agent4_report(status="SUCCESS"),
        _AGENT3_REPORT,
        evaluation_id="eval-1",
    )
    assert result["status"] == "CALIBRATION_SUPPORTED"
    assert result["fit_quality"]["objective_after"] == 1.0
    assert result["parameter_uncertainty"][0]["target_id"] == "k1"


def test_map_exposes_standard_error_and_sorts_correlation_pairs():
    result = map_calibration_result_to_module_evaluation(
        _REQUEST_DICT,
        _agent4_report(
            status="SUCCESS",
            parameter_estimates=[
                {
                    "target_kind": "PARAMETER",
                    "target_id": "k1",
                    "original_value": 0.1,
                    "original_source": "HEURISTIC_INITIALIZATION",
                    "fitted_value": 0.7,
                    "lower_bound": 0.001,
                    "upper_bound": 5.0,
                    "at_lower_bound": False,
                    "at_upper_bound": False,
                    "new_source": "CALIBRATED",
                    "provenance_refs": [],
                    "standard_error": 0.05,
                }
            ],
            # Agent 4's own pairs are in target *index* order, not lexicographic -- "k2" before
            # "k1" here, to confirm the harness always re-sorts rather than trusting input order.
            parameter_correlations=[
                {"target_id_a": "k2", "target_id_b": "k1", "correlation": -0.9}
            ],
        ),
        _AGENT3_REPORT,
        evaluation_id="eval-1",
    )
    assert result["parameter_uncertainty"][0]["standard_error"] == 0.05
    assert result["parameter_correlations"] == [
        {"target_id_a": "k1", "target_id_b": "k2", "correlation": -0.9}
    ]


def test_map_insufficient_data_discloses_no_evidence():
    result = map_calibration_result_to_module_evaluation(
        _REQUEST_DICT,
        _agent4_report(status="INSUFFICIENT_DATA"),
        _AGENT3_REPORT,
        evaluation_id="eval-1",
    )
    assert result["status"] == "INSUFFICIENT_DATA"
    assert "fit_quality" not in result
    assert "parameter_uncertainty" not in result


def test_map_unidentifiable_is_available_evidence_not_missing():
    result = map_calibration_result_to_module_evaluation(
        _REQUEST_DICT,
        _agent4_report(status="UNIDENTIFIABLE"),
        _AGENT3_REPORT,
        evaluation_id="eval-1",
    )
    assert result["status"] == "UNIDENTIFIABLE"
    assert result["fit_quality"] is not None


@pytest.mark.parametrize("agent4_status", ["OPTIMIZATION_FAILED", "SIMULATION_FAILED"])
def test_map_failure_statuses_to_calibration_failed(agent4_status):
    result = map_calibration_result_to_module_evaluation(
        _REQUEST_DICT,
        _agent4_report(status=agent4_status),
        _AGENT3_REPORT,
        evaluation_id="eval-1",
    )
    assert result["status"] == "CALIBRATION_FAILED"


def test_map_invalid_request_raises_never_a_disclosed_outcome():
    with pytest.raises(ModuleCalibrationWorkflowError):
        map_calibration_result_to_module_evaluation(
            _REQUEST_DICT,
            _agent4_report(status="INVALID_REQUEST"),
            _AGENT3_REPORT,
            evaluation_id="eval-1",
        )


def test_map_boundary_sensitivity_findings_filtered_by_category():
    result = map_calibration_result_to_module_evaluation(
        _REQUEST_DICT,
        _agent4_report(
            status="SUCCESS",
            identifiability_findings=[
                {
                    "finding_id": "f1",
                    "category": "BOUND_HIT",
                    "severity": "WARNING",
                    "summary": "at bound",
                    "explanation": "...",
                    "related_target_ids": ["k1"],
                },
                {
                    "finding_id": "f2",
                    "category": "HIGH_CORRELATION",
                    "severity": "ERROR",
                    "summary": "correlated",
                    "explanation": "...",
                    "related_target_ids": ["k1"],
                },
            ],
        ),
        _AGENT3_REPORT,
        evaluation_id="eval-1",
    )
    assert len(result["identifiability_findings"]) == 2
    assert len(result["boundary_sensitivity_findings"]) == 1
    assert result["boundary_sensitivity_findings"][0]["category"] == "BOUND_HIT"


def test_build_module_agent3_handoff_is_passthrough():
    handoff = _module_handoff()
    request = _request(run_id="passthrough-test", module_handoff=handoff)
    built = build_module_agent3_handoff(request)
    assert built == handoff
    assert built is not handoff  # a copy, never the same mutable object


def test_run_module_calibration_workflow_writes_output_artifacts(tmp_path):
    run_id = f"module-calib-artifacts-{uuid.uuid4().hex[:8]}"
    request = _request(run_id=run_id)
    run_module_calibration_workflow(request, _calibration_request(), stage_dir=tmp_path)
    assert (tmp_path / f"module_agent3_input_{run_id}.json").is_file()
    assert (tmp_path / f"module_agent3_output_{run_id}.json").is_file()
    assert (tmp_path / f"module_agent4_handoff_{run_id}.json").is_file()
    assert (tmp_path / f"module_calibration_result_{run_id}.json").is_file()
    with open(tmp_path / f"module_calibration_result_{run_id}.json") as f:
        persisted = json.load(f)
    assert persisted["run_id"] == run_id
