"""Tests for ``app.harness.invariants``: end-to-end structural checks over gathered artifacts."""

from __future__ import annotations

from app.harness.invariants import (
    check_calibrated_values_distinguishable,
    check_evidence_provenance_survives,
    check_fixed_parameters_never_calibrated,
    check_identifier_traceability,
    check_no_mutation_of_agent2_model,
    check_validation_never_feeds_back,
)

_AGENT2_MODEL = {
    "antimony_text": "model m ... end",
    "species": [{"species_id": "S1"}],
    "reactions": [{"reaction_id": "reaction-1"}],
    "parameters": [
        {"parameter_id": "k1", "source": "HEURISTIC_INITIALIZATION", "fixed": None},
        {"parameter_id": "k_fixed", "source": "CURATED", "fixed": True},
    ],
}


def test_identifier_traceability_passes_for_known_ids():
    agent3 = {
        "diagnostics": [
            {
                "finding_id": "f1",
                "related_species_ids": ["S1"],
                "related_reaction_ids": [],
                "related_parameter_ids": [],
            }
        ]
    }
    agent4 = {"calibration": {"parameter_estimates": [{"target_id": "k1"}]}}
    result = check_identifier_traceability(_AGENT2_MODEL, agent3, agent4)
    assert result.passed is True


def test_identifier_traceability_fails_for_unknown_id():
    agent3 = {
        "diagnostics": [
            {
                "finding_id": "f1",
                "related_species_ids": ["does-not-exist"],
                "related_reaction_ids": [],
                "related_parameter_ids": [],
            }
        ]
    }
    result = check_identifier_traceability(_AGENT2_MODEL, agent3, None)
    assert result.passed is False
    assert "does-not-exist" in result.details


def test_fixed_parameters_never_calibrated_passes_when_untouched():
    agent4 = {"calibration": {"parameter_estimates": [{"target_id": "k1"}]}}
    result = check_fixed_parameters_never_calibrated(_AGENT2_MODEL, agent4)
    assert result.passed is True


def test_fixed_parameters_never_calibrated_fails_when_violated():
    agent4 = {"calibration": {"parameter_estimates": [{"target_id": "k_fixed"}]}}
    result = check_fixed_parameters_never_calibrated(_AGENT2_MODEL, agent4)
    assert result.passed is False
    assert "k_fixed" in result.details


def test_calibrated_values_distinguishable_passes_for_well_formed_estimate():
    agent4 = {
        "calibration": {
            "parameter_estimates": [
                {
                    "target_id": "k1",
                    "new_source": "CALIBRATED",
                    "fitted_value": 0.5,
                    "original_value": 0.1,
                }
            ]
        }
    }
    result = check_calibrated_values_distinguishable(agent4)
    assert result.passed is True


def test_calibrated_values_distinguishable_fails_for_missing_original_value():
    agent4 = {
        "calibration": {
            "parameter_estimates": [
                {"target_id": "k1", "new_source": "CALIBRATED", "fitted_value": 0.5}
            ]
        }
    }
    result = check_calibrated_values_distinguishable(agent4)
    assert result.passed is False


def test_evidence_provenance_survives_when_source_matches():
    agent4 = {
        "calibration": {
            "parameter_estimates": [
                {"target_id": "k1", "original_source": "HEURISTIC_INITIALIZATION"}
            ]
        }
    }
    result = check_evidence_provenance_survives(_AGENT2_MODEL, agent4)
    assert result.passed is True


def test_evidence_provenance_survives_fails_when_relabeled():
    agent4 = {
        "calibration": {"parameter_estimates": [{"target_id": "k1", "original_source": "CURATED"}]}
    }
    result = check_evidence_provenance_survives(_AGENT2_MODEL, agent4)
    assert result.passed is False


def test_no_mutation_of_agent2_model_passes_when_byte_identical():
    stage2 = {"antimony_text": "same text"}
    stage5_input = {"antimony_text": "same text"}
    result = check_no_mutation_of_agent2_model(stage2, stage5_input)
    assert result.passed is True


def test_no_mutation_of_agent2_model_fails_when_different():
    stage2 = {"antimony_text": "original"}
    stage5_input = {"antimony_text": "mutated"}
    result = check_no_mutation_of_agent2_model(stage2, stage5_input)
    assert result.passed is False


def test_validation_never_feeds_back_passes_when_byte_identical():
    stage4 = {"calibration": {"parameter_estimates": [{"target_id": "k1", "fitted_value": 0.5}]}}
    stage5_input = {
        "calibration": {"parameter_estimates": [{"target_id": "k1", "fitted_value": 0.5}]}
    }
    result = check_validation_never_feeds_back(stage4, stage5_input)
    assert result.passed is True


def test_validation_never_feeds_back_fails_when_estimates_differ():
    stage4 = {"calibration": {"parameter_estimates": [{"target_id": "k1", "fitted_value": 0.5}]}}
    stage5_input = {
        "calibration": {"parameter_estimates": [{"target_id": "k1", "fitted_value": 0.6}]}
    }
    result = check_validation_never_feeds_back(stage4, stage5_input)
    assert result.passed is False
