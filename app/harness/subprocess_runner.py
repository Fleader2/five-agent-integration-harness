"""Invoking one agent's own runner script inside that agent's own venv, as an isolated
subprocess.

**Why subprocess, never import**: every agent repository in this project uses the identical
top-level package name ``app`` (``app.agent1``, ``app.agent2``, ... each rooted at its own
repository). Importing two of them in the same Python process is not just against this
project's own established decoupling convention -- it is not even possible without colliding
``sys.modules`` entries. Running each stage as a separate subprocess, with that agent's own
``.venv/bin/python3`` interpreter and that agent's own repository as the working directory, is
therefore not a stylistic choice but a structural necessity, and happens to also be exactly
what "the harness orchestrates existing agents; it does not duplicate agent logic" means in
practice: the harness never re-implements what an agent's runner script does, it only starts
it, waits for it, and reads back the file it wrote.
"""

from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class SubprocessStageOutcome:
    returncode: int
    stdout: str
    stderr: str
    elapsed_seconds: float
    timed_out: bool


def run_stage_subprocess(
    *,
    venv_python: str | Path,
    script_path: str | Path,
    cwd: str | Path,
    args: list[str],
    timeout_seconds: float = 300.0,
) -> SubprocessStageOutcome:
    """Run ``script_path`` with ``venv_python`` from ``cwd``, passing ``args``. Never raises for
    a non-zero exit or a timeout -- both are reported as data in the returned outcome, exactly
    like every agent's own "report, never raise, for an expected outcome" convention.

    ``PYTHONPATH`` is explicitly set to ``cwd`` (the target agent's own repository root) --
    Python's default ``sys.path[0]`` is the *script's own* containing directory (this harness
    repository), never the subprocess's working directory, so without this the agent's own
    ``app.agentN`` package would not be importable at all inside the runner script.
    """
    started = time.monotonic()
    env = dict(os.environ)
    env["PYTHONPATH"] = str(cwd)
    try:
        completed = subprocess.run(
            [str(venv_python), str(script_path), *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
            env=env,
        )
        elapsed = time.monotonic() - started
        return SubprocessStageOutcome(
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            elapsed_seconds=elapsed,
            timed_out=False,
        )
    except subprocess.TimeoutExpired as exc:
        elapsed = time.monotonic() - started
        return SubprocessStageOutcome(
            returncode=-1,
            stdout=exc.stdout or "",
            stderr=(exc.stderr or "") + f"\nStage timed out after {timeout_seconds:g}s.",
            elapsed_seconds=elapsed,
            timed_out=True,
        )


__all__ = ["SubprocessStageOutcome", "run_stage_subprocess"]
