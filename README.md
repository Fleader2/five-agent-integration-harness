# Five-Agent End-to-End Integration Harness

## Overview

This repository orchestrates the five agents of the biochemical-modeling pipeline —
`agent1-biochemical-curator` → `agent2-antimony-builder` → `agent3-simulation-diagnostics` →
`agent4-calibration-estimator` → `agent5-validation-experimental-design` — across serialized
JSON contracts, and verifies the complete workflow operates correctly across repository
boundaries.

**Central rule:** the integration harness orchestrates existing agents; it does not duplicate
agent logic or silently repair their outputs.

Every agent runs as an isolated subprocess, in its own venv, with its own repository as `cwd`.
The harness's own code has **zero runtime dependencies** — it only reads/writes JSON files and
shells out.

See `docs/01_orchestration_architecture.md` through `docs/06_version1_success_criteria.md` for
full detail, including two disclosed scope decisions worth reading before trusting any run's own
output: how the Agent 1 → Agent 2 boundary is handled (consumed artifact + one live, cheap
boundary check, never a blind hand-chained re-invocation of Agent 2's own eleven-plus-stage
internal pipeline), and why three sibling repositories independently named the same real
contract shape three different things.

## Two canonical fixtures

* **Fixture A** — the real `sce00061` (yeast fatty-acid-biosynthesis) workflow. Expected result:
  `SUCCESS_WITH_EXPECTED_DATA_GAPS` (Agent 4/Agent 5 honestly report insufficient real data).
* **Fixture B** — a fully synthetic, known-ground-truth reaction chain. Expected result:
  `SUCCESS`, with Agent 4 genuinely recovering the two well-identified true parameters and
  flagging the deliberately-poorly-identified third, and Agent 5 genuinely ranking the
  known-informative next experiment at the top.

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"

.venv/bin/python3 scripts/run_fixture_a.py   # requires Agent 1's live database
.venv/bin/python3 scripts/run_fixture_b.py   # no external dependencies beyond the sibling venvs
```

See `docs/05_running_the_fixtures.md` for prerequisites and what each fixture proves.

## Tests

```bash
.venv/bin/python3 -m pytest tests/ -q
```

The real-`sce00061` test module (`tests/harness/test_real_sce00061_workflow.py`) is skipped
automatically if Agent 1's live database is not reachable; every other test requires only the
five sibling repositories' own venvs to exist at the standard sibling-directory location.
