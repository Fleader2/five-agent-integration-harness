"""Where each sibling agent repository lives, and its own venv interpreter.

All five agent repositories and this harness are siblings under the same parent directory --
confirmed the established layout throughout this project's own history. A real deployment would
make this configurable (an environment variable, a config file); Version 1 hard-codes the
sibling-directory convention already in effect for every repository this session has built,
and fails loudly (``WorkflowStatus.BLOCKED``, never a guess) if a path does not actually exist.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

_PROJECTS_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True, slots=True)
class AgentRepo:
    label: str
    repo_dir: Path
    venv_python: Path


def _repo(label: str, dirname: str) -> AgentRepo:
    repo_dir = _PROJECTS_ROOT / dirname
    return AgentRepo(
        label=label, repo_dir=repo_dir, venv_python=repo_dir / ".venv" / "bin" / "python3"
    )


AGENT1 = _repo("Agent 1", "agent1-biochemical-curator")
AGENT2 = _repo("Agent 2", "agent2-antimony-builder")
AGENT3 = _repo("Agent 3", "agent3-simulation-diagnostics")
AGENT4 = _repo("Agent 4", "agent4-calibration-estimator")
AGENT5 = _repo("Agent 5", "agent5-validation-experimental-design")


def check_repo_available(repo: AgentRepo) -> str | None:
    """``None`` if ``repo`` is usable; otherwise a human-readable reason it is not."""
    if not repo.repo_dir.is_dir():
        return f"{repo.label}'s repository directory does not exist: {repo.repo_dir}"
    if not repo.venv_python.is_file():
        return f"{repo.label}'s venv interpreter does not exist: {repo.venv_python}"
    return None


__all__ = ["AGENT1", "AGENT2", "AGENT3", "AGENT4", "AGENT5", "AgentRepo", "check_repo_available"]
