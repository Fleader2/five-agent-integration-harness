"""The real sce00061 (yeast fatty-acid-biosynthesis) full-workflow test.

**Hermetic Harness real-workflow test hardening.** This test no longer depends on the mutable
developer ``agent1`` database having been pre-populated by some earlier, untracked, ad-hoc
pilot run. Before the real five-stage workflow runs, the module-scoped ``real_workflow_report``
fixture below provisions its own disposable Postgres database (a uniquely-named database,
migrated to head with Agent 1's own real Alembic chain, then seeded by a real, live run of
Agent 1's own curation pipeline -- see ``agent1-biochemical-curator/scripts
/sce00061_fixture.py``'s own module docstring for the full recovery/provisioning design and
``agent1-biochemical-curator/docs/32_sce00061_fixture_recovery.md`` for the incident this
replaces), and points Stage 1's own Agent 1 subprocess invocation at it via a ``DATABASE_URL``
environment override -- never by
modifying ``app.harness.pipeline``/``subprocess_runner`` themselves, since both already forward
the calling process's own environment unchanged. The database is dropped in the fixture's own
teardown, leaving no persistent contamination. Agent 1's own curation logic is never mocked;
this only removes this test's dependency on *pre-existing* developer data.

**Five-Agent Workflow V1 Hardening increment:** Stage 2 (Agent 2) is now a genuine, live
subprocess invocation of Agent 2's own canonical orchestration entrypoint against this exact
run's own freshly-curated Agent 1 output -- never a copy of a pre-existing, already-committed
Agent 2 artifact.

The full five-stage run is genuinely expensive (provisioning a database, a real live
multi-connector curation run, plus five real agent subprocess invocations) -- run **once** per
test session via a module-scoped fixture, and every test below only asserts against that one
shared result, rather than each re-running the whole workflow independently.
"""

from __future__ import annotations

import json
import os
import subprocess
import uuid
from pathlib import Path

import pytest

from app.harness import repo_paths
from app.harness.pipeline import run_workflow
from app.harness.subprocess_runner import run_stage_subprocess
from app.harness.types import WorkflowRunRequest, WorkflowStatus

_FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
_RUNNERS_DIR = Path(__file__).resolve().parent.parent.parent / "app" / "harness" / "runners"
_FIXTURE_SCRIPT = "scripts/sce00061_fixture.py"
_PROVISION_TIMEOUT_SECONDS = 1800.0


def _db_reachable() -> bool:
    """A pure-stdlib TCP reachability check -- never imports ``psycopg`` directly, since the
    harness's own venv deliberately has zero runtime dependencies (see ``app.harness
    .subprocess_runner``'s own docstring) and does not install Agent 1's database driver."""
    import socket

    try:
        with socket.create_connection(("localhost", 5432), timeout=2):
            return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(
    repo_paths.check_repo_available(repo_paths.AGENT1) is not None or not _db_reachable(),
    reason="A Postgres server reachable by Agent 1 is not available in this environment.",
)


def _run_fixture_script(*args: str) -> subprocess.CompletedProcess[str]:
    """Invoke ``agent1-biochemical-curator/scripts/sce00061_fixture.py`` with Agent 1's own
    venv interpreter and repository as ``cwd`` -- the identical subprocess-isolation pattern
    ``app.harness.subprocess_runner.run_stage_subprocess`` already uses for every real agent
    invocation, reused here directly since this call itself needs no stage bookkeeping."""
    return subprocess.run(
        [str(repo_paths.AGENT1.venv_python), _FIXTURE_SCRIPT, *args],
        cwd=str(repo_paths.AGENT1.repo_dir),
        capture_output=True,
        text=True,
        timeout=_PROVISION_TIMEOUT_SECONDS,
        check=False,
    )


def _discover_a_real_parameter_id(organism_id: str, tmp_dir: Path) -> str:
    """One real, live Agent 1 -> Agent 2 subprocess pass (the exact same runners
    ``run_workflow`` itself calls internally, via the same public
    ``run_stage_subprocess``) against the already-provisioned, already-curated hermetic
    database, purely to discover one real, currently-valid parameter id.

    Needed because ``tests/fixtures/sce00061_calibration_request.json`` targets Agent 4 at one
    specific ``parameter_id`` -- and every fresh curation run assigns fresh random entity ids,
    so a hardcoded id from a past run can never match a newly-provisioned database (confirmed
    directly: it previously made every fresh run's own Agent 4 stage honestly report
    ``INVALID_REQUEST``, never the intended "valid target, no real observation data"
    ``INSUFFICIENT_DATA`` case this fixture's own ``request_id``/``observation_set_id`` names
    document as the actual intent). Agent 1's data is already fixed by the time this runs
    (curation already happened in ``provision``, not here), and both Agent 1's export and
    Agent 2's pipeline are already-documented-deterministic pure functions of that fixed data,
    so the parameter id discovered here is guaranteed to reappear, identically, when
    ``run_workflow`` itself re-runs Stage 1/Stage 2 moments later.
    """
    stage1_output = tmp_dir / "discovery_stage1_output.json"
    stage2_output = tmp_dir / "discovery_stage2_output.json"

    outcome1 = run_stage_subprocess(
        venv_python=repo_paths.AGENT1.venv_python,
        script_path=_RUNNERS_DIR / "run_agent1.py",
        cwd=repo_paths.AGENT1.repo_dir,
        args=["--organism-id", organism_id, "--output", str(stage1_output)],
    )
    if outcome1.returncode != 0:
        pytest.skip(f"Could not run Agent 1 for parameter-id discovery: {outcome1.stderr[-2000:]}")

    outcome2 = run_stage_subprocess(
        venv_python=repo_paths.AGENT2.venv_python,
        script_path=_RUNNERS_DIR / "run_agent2.py",
        cwd=repo_paths.AGENT2.repo_dir,
        args=["--input", str(stage1_output), "--output", str(stage2_output)],
    )
    if outcome2.returncode != 0:
        pytest.skip(f"Could not run Agent 2 for parameter-id discovery: {outcome2.stderr[-2000:]}")

    with open(stage2_output) as f:
        agent2_model = json.load(f)
    # Agent 4's own eligibility policy (``agent4-calibration-estimator/app/agent4
    # /eligibility.py``) refuses, by design, to calibrate a parameter whose own ``source`` is
    # evidence-backed (``LITERATURE_DERIVED``/``CURATED``/``AI_PREDICTED``/...) or ``fixed``,
    # unless the request explicitly authorizes it -- which this fixture's own request
    # deliberately never does (see ``tests/fixtures/sce00061_calibration_request.json``'s own
    # empty ``authorized_provenance_classes``/``authorized_parameter_ids``). Picking an
    # arbitrary parameter id therefore sometimes, legitimately, produces Agent 4's *different*
    # honest rejection (``INVALID_REQUEST`` for an ineligible target) instead of the
    # ``INSUFFICIENT_DATA`` this fixture's own naming documents as its actual intent --
    # confirmed directly: the same discovery logic without this filter intermittently failed
    # this way. Restrict the pool to the same default-calibratable sources Agent 4 itself
    # grants no-authorization-needed status.
    _DEFAULT_CALIBRATABLE_SOURCES = {"HEURISTIC_INITIALIZATION", "PLACEHOLDER", "DEFAULT"}
    eligible = [
        p["parameter_id"]
        for p in agent2_model["parameters"]
        if p["source"] in _DEFAULT_CALIBRATABLE_SOURCES and p["fixed"] is not True
    ]
    if not eligible:
        pytest.skip(
            "Freshly-curated sce00061 data produced zero default-calibratable (unprotected, "
            "not fixed) Agent 2 parameters."
        )
    return sorted(eligible)[0]


@pytest.fixture(scope="module")
def real_workflow_report(tmp_path_factory):
    database_name = f"agent1_harness_fixture_{uuid.uuid4().hex[:12]}"
    discovery_dir = tmp_path_factory.mktemp("real-sce00061-discovery")

    provisioned = _run_fixture_script("provision", "--database-name", database_name)
    if provisioned.returncode != 0:
        pytest.skip(
            f"Could not provision the hermetic sce00061 fixture database: "
            f"{provisioned.stderr.strip()[-2000:]}"
        )
    summary = json.loads(provisioned.stdout.strip().splitlines()[-1])

    previous_database_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = summary["database_url"]
    try:
        real_parameter_id = _discover_a_real_parameter_id(summary["organism_id"], discovery_dir)

        with open(_FIXTURES / "sce00061_calibration_request.json") as f:
            stage4_request = json.load(f)
        stage4_request["targets"][0]["target_id"] = real_parameter_id
        with open(_FIXTURES / "sce00061_validation_request.json") as f:
            stage5_request = json.load(f)
        stage_directory = tmp_path_factory.mktemp("real-sce00061") / "real-sce00061-test"
        request = WorkflowRunRequest(
            run_id="real-sce00061-test",
            fixture_name="sce00061_real",
            stage_directory=str(stage_directory),
        )
        return run_workflow(
            request,
            stage1_organism_id=summary["organism_id"],
            stage4_request=stage4_request,
            stage5_request=stage5_request,
        )
    finally:
        if previous_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_database_url
        _run_fixture_script("teardown", "--database-name", database_name)


def test_real_workflow_completes_with_expected_data_gaps(real_workflow_report):
    assert real_workflow_report.overall_status is WorkflowStatus.SUCCESS_WITH_EXPECTED_DATA_GAPS
    assert len(real_workflow_report.stages) == 5


def test_real_workflow_agent1_curates_real_data(real_workflow_report):
    """``reactions``/``kinetic_measurements`` reflect a real, live curation run against today's
    external sources, via ``agent1-biochemical-curator/scripts/sce00061_fixture.py`` -- *not*
    any specific historical pilot run. ``reactions`` (KEGG's own stable pathway membership) has
    stayed exactly 38 across every run observed so far; ``kinetic_measurements`` is lower than
    this project's own historical high-water mark of 216 because that number was reached with
    two more connectors (GotEnzymes2, the Open Enzyme Database) this script's own module
    docstring documents as live-unreachable/degraded when it was written -- re-verify and update
    this number (never silently) if either connector's own live availability changes, per
    ``agent1-biochemical-curator/docs/32_sce00061_fixture_recovery.md``."""
    agent1_stage = real_workflow_report.stages[0]
    assert agent1_stage.status is WorkflowStatus.SUCCESS
    findings = dict(f.split("=") for f in agent1_stage.findings_summary)
    assert int(findings["reactions"]) == 38
    assert int(findings["kinetic_measurements"]) == 72


def test_real_workflow_agent2_reports_executable(real_workflow_report):
    """``reactions`` has stayed exactly 38 across every independent real run observed so far
    (KEGG's own pathway membership is rigid). ``species`` was exactly 53 (compound species
    only) before the Explicit Enzyme Concentration Representation increment; it is now 66 --
    53 compound species + one explicit catalytic-enzyme species per each of this organism's
    13 curated proteins (ACC1, HFA1, FAS1, FAS2, CEM1, ETR1, FAA1-4, MCT1, OAR1, HTD2), all 13
    resolving to a single uniform reaction compartment (cytosol) and therefore all 13 getting
    exactly one species each (``app.agent2.enzyme_concentration_species
    .build_enzyme_concentration_species``'s own dedup-by-(protein, compartment) rule).
    ``parameters`` is intentionally a floor, not an exact equality: observed values of
    87 and 91 across two otherwise-identical independent live runs (same reaction/kinetic-
    measurement counts both times) show Agent 2's own parameter-consolidation stage is
    sensitive to some real, legitimate variation in the live kinetic evidence Agent 1 supplies
    it run to run (tie-breaking among near-duplicate measurements, isozyme/enzyme-state
    resolution order, ...) -- never a fabricated or zero/trivial parameter set, which is all
    this assertion is actually responsible for proving."""
    agent2_stage = real_workflow_report.stages[1]
    findings = dict(f.split("=") for f in agent2_stage.findings_summary)
    assert findings["readiness"] == "EXECUTABLE"
    assert int(findings["species"]) == 66
    assert int(findings["reactions"]) == 38
    assert int(findings["parameters"]) >= 80
    assert agent2_stage.elapsed_seconds is not None


def test_real_workflow_agent3_diagnoses_real_model(real_workflow_report):
    agent3_stage = real_workflow_report.stages[2]
    assert any("overall_status=" in f for f in agent3_stage.findings_summary)


def test_real_workflow_agent4_honestly_reports_insufficient_data(real_workflow_report):
    agent4_stage = real_workflow_report.stages[3]
    assert agent4_stage.status is WorkflowStatus.SUCCESS_WITH_EXPECTED_DATA_GAPS
    assert "calibration_status=INSUFFICIENT_DATA" in agent4_stage.findings_summary


def test_real_workflow_agent5_honestly_reports_insufficient_validation_data(real_workflow_report):
    agent5_stage = real_workflow_report.stages[4]
    assert agent5_stage.status is WorkflowStatus.SUCCESS_WITH_EXPECTED_DATA_GAPS
    assert "overall_status=INSUFFICIENT_VALIDATION_DATA" in agent5_stage.findings_summary


def test_real_workflow_all_invariants_pass(real_workflow_report):
    assert all(c.passed for c in real_workflow_report.invariant_checks)


def test_real_workflow_never_fabricates_success(real_workflow_report):
    """The central assertion this fixture exists to make: an honest data gap is never silently
    converted into an unqualified SUCCESS."""
    assert real_workflow_report.overall_status is not WorkflowStatus.SUCCESS
    assert real_workflow_report.overall_status is WorkflowStatus.SUCCESS_WITH_EXPECTED_DATA_GAPS
