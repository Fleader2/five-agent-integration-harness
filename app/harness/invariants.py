"""End-to-end invariant checks across the whole gathered set of stage artifacts.

Every check here reads already-written stage artifact files and asks a single yes/no structural
question -- never a per-stage diagnostic (those belong to each stage's own
``WorkflowStageResult``). A failed invariant here means the *orchestration itself* let something
through it should not have -- a genuine harness-level defect, not an agent reporting an honest
data gap.
"""

from __future__ import annotations

from app.harness.types import InvariantCheckResult


def _entity_ids(agent2_model: dict) -> set[str]:
    ids: set[str] = set()
    ids.update(s["species_id"] for s in agent2_model.get("species", []))
    ids.update(r["reaction_id"] for r in agent2_model.get("reactions", []))
    ids.update(p["parameter_id"] for p in agent2_model.get("parameters", []))
    return ids


def check_identifier_traceability(
    agent2_model: dict, agent3_report: dict | None, agent4_report: dict | None
) -> InvariantCheckResult:
    known_ids = _entity_ids(agent2_model)
    unknown: list[str] = []

    for finding in (agent3_report or {}).get("diagnostics", []):
        for entity_id in (
            list(finding.get("related_species_ids", []))
            + list(finding.get("related_reaction_ids", []))
            + list(finding.get("related_parameter_ids", []))
        ):
            if entity_id not in known_ids:
                unknown.append(f"agent3 finding {finding.get('finding_id')} -> {entity_id!r}")

    for estimate in (agent4_report or {}).get("calibration", {}).get("parameter_estimates", []):
        if estimate["target_id"] not in known_ids:
            unknown.append(f"agent4 estimate -> {estimate['target_id']!r}")

    passed = not unknown
    return InvariantCheckResult(
        check_id="identifier-traceability",
        passed=passed,
        description=(
            "Every reaction/species/parameter id referenced by a downstream stage's own "
            "finding or estimate exists in the original Agent 2 model."
        ),
        details="All referenced ids resolved." if passed else "; ".join(unknown),
    )


def check_fixed_parameters_never_calibrated(
    agent2_model: dict, agent4_report: dict | None
) -> InvariantCheckResult:
    fixed_ids = {
        p["parameter_id"] for p in agent2_model.get("parameters", []) if p.get("fixed") is True
    }
    calibrated_ids = {
        e["target_id"]
        for e in (agent4_report or {}).get("calibration", {}).get("parameter_estimates", [])
    }
    violated = fixed_ids & calibrated_ids
    passed = not violated
    return InvariantCheckResult(
        check_id="fixed-parameters-never-calibrated",
        passed=passed,
        description="No parameter Agent 2 declared fixed=True was ever calibrated by Agent 4.",
        details=f"{len(fixed_ids)} fixed parameter(s) declared, 0 calibrated."
        if passed
        else f"Violated: {violated}",
    )


def check_calibrated_values_distinguishable(agent4_report: dict | None) -> InvariantCheckResult:
    estimates = (agent4_report or {}).get("calibration", {}).get("parameter_estimates", [])
    bad = [
        e["target_id"]
        for e in estimates
        if e.get("new_source") != "CALIBRATED"
        or "fitted_value" not in e
        or "original_value" not in e
    ]
    passed = not bad
    return InvariantCheckResult(
        check_id="calibrated-values-distinguishable",
        passed=passed,
        description=(
            "Every Agent 4 parameter estimate carries both its original value/source and its "
            "new_source='CALIBRATED' fitted value side by side -- never overwritten in place."
        ),
        details=f"{len(estimates)} estimate(s) checked." if passed else f"Malformed: {bad}",
    )


def check_evidence_provenance_survives(
    agent2_model: dict, agent4_report: dict | None
) -> InvariantCheckResult:
    params_by_id = {p["parameter_id"]: p for p in agent2_model.get("parameters", [])}
    estimates = (agent4_report or {}).get("calibration", {}).get("parameter_estimates", [])
    mismatched = [
        e["target_id"]
        for e in estimates
        if e["target_id"] in params_by_id
        and e.get("original_source") != params_by_id[e["target_id"]].get("source")
    ]
    passed = not mismatched
    return InvariantCheckResult(
        check_id="evidence-provenance-survives",
        passed=passed,
        description=(
            "Every Agent 4 estimate's own original_source exactly matches the source Agent 2 "
            "originally declared for that parameter -- never re-labeled downstream."
        ),
        details="All sources match." if passed else f"Mismatched: {mismatched}",
    )


def check_no_mutation_of_agent2_model(
    stage2_output: dict, stage5_input_agent2_model: dict | None
) -> InvariantCheckResult:
    if stage5_input_agent2_model is None:
        return InvariantCheckResult(
            check_id="no-mutation-of-agent2-model",
            passed=True,
            description="Agent 5's own input Antimony text is byte-identical to Agent 2's output.",
            details="Agent 5 stage did not run; nothing to compare.",
        )
    passed = stage2_output.get("antimony_text") == stage5_input_agent2_model.get("antimony_text")
    return InvariantCheckResult(
        check_id="no-mutation-of-agent2-model",
        passed=passed,
        description="Agent 5's own input Antimony text is byte-identical to Agent 2's output.",
        details="Byte-identical."
        if passed
        else "Antimony text differs between stage 2 and stage 5 input.",
    )


def check_validation_never_feeds_back(
    stage4_output: dict, stage5_input_agent4_report: dict | None
) -> InvariantCheckResult:
    description = "Agent 5's own input parameter estimates are byte-identical to Agent 4's output."
    if stage5_input_agent4_report is None:
        return InvariantCheckResult(
            check_id="validation-never-feeds-back",
            passed=True,
            description=description,
            details="Agent 5 stage did not run; nothing to compare.",
        )
    original = stage4_output.get("calibration", {}).get("parameter_estimates", [])
    fed_in = stage5_input_agent4_report.get("calibration", {}).get("parameter_estimates", [])
    passed = original == fed_in
    return InvariantCheckResult(
        check_id="validation-never-feeds-back",
        passed=passed,
        description=description,
        details="Byte-identical."
        if passed
        else "Parameter estimates differ between stage 4 and stage 5 input.",
    )


def run_invariant_checks(
    *,
    stage2_output: dict,
    stage3_output: dict | None,
    stage4_output: dict | None,
    stage5_input_agent2_model: dict | None,
    stage5_input_agent4_report: dict | None,
) -> tuple[InvariantCheckResult, ...]:
    """The full Version 1 end-to-end invariant sweep, in a fixed, deterministic order."""
    return (
        check_identifier_traceability(stage2_output, stage3_output, stage4_output),
        check_fixed_parameters_never_calibrated(stage2_output, stage4_output),
        check_calibrated_values_distinguishable(stage4_output),
        check_evidence_provenance_survives(stage2_output, stage4_output),
        check_no_mutation_of_agent2_model(stage2_output, stage5_input_agent2_model),
        check_validation_never_feeds_back(stage4_output, stage5_input_agent4_report),
    )


__all__ = [
    "check_calibrated_values_distinguishable",
    "check_evidence_provenance_survives",
    "check_fixed_parameters_never_calibrated",
    "check_identifier_traceability",
    "check_no_mutation_of_agent2_model",
    "check_validation_never_feeds_back",
    "run_invariant_checks",
]
