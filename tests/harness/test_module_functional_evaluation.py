"""Tests for the Functional Modularity Criteria from Agents 3 and 4 increment's own harness
side: ``app.harness.module_functional_evaluation``.

Mirrors ``tests/harness/test_module_calibration_workflow.py``'s own split: unit tests for the
mapping policy (no subprocess) plus one real, full round trip through Agent 3's own real
pipeline against a genuine three-species chain, confirming the whole wiring (request ->
whole-network Agent2->Agent3 handoff -> Agent 3 subprocess -> mapped result) actually works end
to end, not just on paper.
"""

from __future__ import annotations

import uuid

import pytest

from app.harness.module_functional_evaluation import (
    ModuleFunctionalEvaluationWorkflowError,
    build_agent3_functional_evaluation_input,
    map_functional_result_to_module_evaluation,
    run_module_functional_evaluation_workflow,
)
from app.harness.repo_paths import AGENT3, check_repo_available

pytestmark = pytest.mark.skipif(
    check_repo_available(AGENT3) is not None,
    reason="Agent 3 sibling repo (with its own venv) is not available",
)

# --- Fixtures: a 3-species chain A -> B -> C, module = {A, B, r1}, external = {C, r2} -------


def _whole_network_handoff() -> dict:
    antimony_text = """
    model chain
      compartment C = 1
      species A in C
      species B in C
      species Cc in C
      A = 10
      B = 0
      Cc = 0
      r1: A -> B; k1 * A
      r2: B -> Cc; k2 * B
      k1 = 0.5
      k2 = 0.3
    end
    """
    return {
        "contract_version": "agent2-downstream-v3",
        "model_id": "model::chain",
        "network_id": "model::chain",
        "antimony_text": antimony_text,
        "antimony_generator_version": "antimony-generation-v7",
        "antimony_symbol_map": {
            "species": {"A": "A", "B": "B", "Cc": "Cc"},
            "reactions": {"r1": "r1", "r2": "r2"},
            "parameters": {"k1": "k1", "k2": "k2"},
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
                "species_id": sid,
                "name": sid,
                "compartment_id": "C",
                "source_compound_id": None,
                "source_enzyme_state_id": None,
                "source_protein_id": None,
                "initial_amount": None,
                "initial_concentration": str(val),
                "constant": False,
                "boundary_condition": False,
                "initialization_source": None,
            }
            for sid, val in (("A", 10), ("B", 0), ("Cc", 0))
        ],
        "reactions": [
            {
                "reaction_id": "r1",
                "name": "r1",
                "reversible": False,
                "participants": [
                    {"species_id": "A", "role": "REACTANT", "stoichiometry": "1"},
                    {"species_id": "B", "role": "PRODUCT", "stoichiometry": "1"},
                ],
            },
            {
                "reaction_id": "r2",
                "name": "r2",
                "reversible": False,
                "participants": [
                    {"species_id": "B", "role": "REACTANT", "stoichiometry": "1"},
                    {"species_id": "Cc", "role": "PRODUCT", "stoichiometry": "1"},
                ],
            },
        ],
        "kinetic_laws": [
            {
                "kinetic_law_id": "kl-r1",
                "reaction_id": "r1",
                "law_type": "MASS_ACTION",
                "expression": "k1 * A",
                "parameter_ids": ["k1"],
                "species_ids": ["A"],
                "enzyme_state_id": None,
                "protein_id": None,
                "complex_id": None,
                "rate_law_scope": "LUMPED_EFFECTIVE_RATE",
                "assumptions": [],
            },
            {
                "kinetic_law_id": "kl-r2",
                "reaction_id": "r2",
                "law_type": "MASS_ACTION",
                "expression": "k2 * B",
                "parameter_ids": ["k2"],
                "species_ids": ["B"],
                "enzyme_state_id": None,
                "protein_id": None,
                "complex_id": None,
                "rate_law_scope": "LUMPED_EFFECTIVE_RATE",
                "assumptions": [],
            },
        ],
        "parameters": [
            {
                "parameter_id": pid,
                "name": pid,
                "source": "CURATED",
                "value": str(val),
                "unit": None,
                "reaction_id": rid,
                "kinetic_law_assignment_id": None,
                "uncertainty_text": None,
                "provenance_refs": [],
                "lower_bound": None,
                "upper_bound": None,
                "fixed": False,
            }
            for pid, val, rid in (("k1", 0.5, "r1"), ("k2", 0.3, "r2"))
        ],
        "model_assumptions": [],
    }


def _request(*, run_id: str) -> dict:
    return {
        "request_id": f"functional-eval-request::{run_id}",
        "correlation_id": f"corr::{run_id}",
        "run_id": run_id,
        "parent_model_id": "model::chain",
        "modularization_id": "mz-1",
        "module_id": "mod-ab",
        "whole_network_handoff": _whole_network_handoff(),
        "baseline_request": {
            "request_id": "baseline",
            "start_time": 0.0,
            "end_time": 20.0,
            "num_points": 50,
            "integrator": "cvode",
            "absolute_tolerance": 1e-10,
            "relative_tolerance": 1e-8,
        },
        "perturbation_targets": [
            {"target_kind": "PARAMETER", "target_id": "k1", "fraction": "0.1", "is_internal": True},
            {
                "target_kind": "PARAMETER",
                "target_id": "k2",
                "fraction": "0.1",
                "is_internal": False,
            },
        ],
        "requested_at": None,
    }


# --- Real, full round trip --------------------------------------------------------------------


def test_full_round_trip_reports_per_species_effects(tmp_path):
    run_id = f"functional-eval-success-{uuid.uuid4().hex[:8]}"
    request = _request(run_id=run_id)
    result = run_module_functional_evaluation_workflow(request, stage_dir=tmp_path)
    assert result["status"] == "EVALUATED"
    assert len(result["perturbation_effects"]) == 2

    internal_effect = next(e for e in result["perturbation_effects"] if e["target_id"] == "k1")
    external_effect = next(e for e in result["perturbation_effects"] if e["target_id"] == "k2")
    assert internal_effect["is_internal"] is True
    assert external_effect["is_internal"] is False
    assert internal_effect["simulation_status"] == "SUCCESS"
    assert internal_effect["remained_numerically_stable"] is True

    # Perturbing k1 (upstream of A -> B) must move B and Cc (downstream propagation) --
    # confirms per-species data genuinely reaches this boundary, not just one scalar.
    assert set(internal_effect["relative_change_by_species"]) >= {"A", "B", "Cc"}
    assert internal_effect["relative_change_by_species"]["A"] > 0

    # Perturbing k2 (downstream of B -> C) must barely move A at all (A has no real path
    # depending on k2 -- any nonzero value here is pure integrator noise, not a genuine
    # dependency) -- a genuine, checkable near-zero-effect case, contrasted against k1's own
    # genuine, large effect on A above.
    assert external_effect["relative_change_by_species"]["A"] < 1e-6


def test_persistence_replay_does_not_rerun_agent3(tmp_path):
    run_id = f"functional-eval-replay-{uuid.uuid4().hex[:8]}"
    request = _request(run_id=run_id)
    first = run_module_functional_evaluation_workflow(request, stage_dir=tmp_path)

    for pattern in (
        "functional_evaluation_agent3_input_*",
        "functional_evaluation_agent3_output_*",
    ):
        for p in tmp_path.glob(f"{pattern}{run_id}.json"):
            p.unlink()

    second = run_module_functional_evaluation_workflow(request, stage_dir=tmp_path)
    assert second == first


def test_agent3_infrastructure_failure_raises_never_disclosed_as_evidence(tmp_path):
    run_id = f"functional-eval-infra-fail-{uuid.uuid4().hex[:8]}"
    request = _request(run_id=run_id)
    broken_handoff = dict(request["whole_network_handoff"])
    del broken_handoff["contract_version"]
    request = {**request, "whole_network_handoff": broken_handoff}
    with pytest.raises(ModuleFunctionalEvaluationWorkflowError):
        run_module_functional_evaluation_workflow(request, stage_dir=tmp_path)
    assert not (tmp_path / f"functional_evaluation_result_{run_id}.json").is_file()


# --- Unit tests: mapping policy (no subprocess) ------------------------------------------------


def test_build_agent3_functional_evaluation_input_is_a_passthrough_shape():
    request = _request(run_id="r1")
    agent3_input = build_agent3_functional_evaluation_input(request)
    assert agent3_input["agent2_model"] == request["whole_network_handoff"]
    assert agent3_input["perturbation_specs"] == [
        {"target_kind": "PARAMETER", "target_id": "k1", "fraction": 0.1},
        {"target_kind": "PARAMETER", "target_id": "k2", "fraction": 0.1},
    ]


def test_map_unsupported_analysis_when_whole_network_fails_to_load():
    request = _request(run_id="r1")
    agent3_report = {
        "report_id": "report-1",
        "overall_status": "MODEL_LOAD_FAILED",
        "perturbations": [],
    }
    result = map_functional_result_to_module_evaluation(
        request, agent3_report, evaluation_id="eval-1"
    )
    assert result["status"] == "UNSUPPORTED_ANALYSIS"
    assert result["perturbation_effects"] == []


def test_map_raises_on_target_count_mismatch():
    request = _request(run_id="r1")
    agent3_report = {
        "report_id": "report-1",
        "overall_status": "SUCCESS",
        "perturbations": [
            {
                "spec": {"target_kind": "PARAMETER", "target_id": "k1"},
                "simulation_status": "SUCCESS",
                "remained_numerically_stable": True,
                "relative_change_by_species": {"A": 0.1},
            }
        ],
    }
    with pytest.raises(ModuleFunctionalEvaluationWorkflowError):
        map_functional_result_to_module_evaluation(request, agent3_report, evaluation_id="eval-1")
