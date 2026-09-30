"""The harness's own exception hierarchy.

Mirrors every sibling agent repository's own per-package error convention: a narrow, typed
hierarchy raised only for genuine structural problems in the harness's own orchestration code
-- never used to represent a stage's own outcome (a contract mismatch, an agent stage failure,
an honest ``INSUFFICIENT_DATA``-style result are all reported as data --
``WorkflowStatus``/``WorkflowStageResult`` -- never raised as Python exceptions, since they are
expected, first-class outcomes this package exists to record and stop cleanly on, not
programming errors).
"""

from __future__ import annotations


class HarnessError(Exception):
    """Base class for every exception this package raises."""


class StageInvocationError(HarnessError):
    """Raised only when a stage could not even be *attempted* (the agent's own venv/repo path
    does not exist, the runner script is missing, the subprocess could not be started at all).
    A stage that ran and failed on its own terms is never raised as this exception -- it is
    reported as ``WorkflowStatus.AGENT_STAGE_FAILED`` in the resulting
    ``WorkflowStageResult``.
    """


__all__ = ["HarnessError", "StageInvocationError"]
