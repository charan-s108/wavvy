"""
Workflow engine — transition table runner + tenant config helpers.

WorkflowRunner.advance(step, key) is the single entry point for all tool-outcome
routing. It looks up (step, key) in definitions.STEP_TRANSITIONS, records the step
in WorkflowProgress, and returns a StepOutcome with a directive message and metadata.
Wrappers in agent_tools.py call advance() and return outcome.message — no if/else.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


# ── Tenant config helpers (unchanged) ────────────────────────────────────────

def get_workflow(name: str) -> dict | None:
    """Return the workflow config dict for the given workflow name, or None."""
    try:
        from config_loader import get_config
        return get_config().workflow_configs.get(name)
    except Exception:
        return None


def get_allowed_tools(workflow_name: str) -> list[str]:
    """Return the list of tools allowed in a given workflow."""
    wf = get_workflow(workflow_name)
    return wf.get("allowed_tools", []) if wf else []


def should_auto_escalate(workflow_name: str, trigger: str) -> bool:
    """Return True if the given trigger should auto-escalate in this workflow."""
    wf = get_workflow(workflow_name)
    return trigger in wf.get("auto_escalate_on", []) if wf else False


def requires_verification(workflow_name: str) -> bool:
    """Return True if this workflow requires identity verification before tool use."""
    wf = get_workflow(workflow_name)
    return wf.get("requires_verification", False) if wf else False


# ── WorkflowRunner ────────────────────────────────────────────────────────────

@dataclass
class StepOutcome:
    message: str
    requires_consent: bool = False
    is_terminal: bool = False
    escalation_team: Optional[str] = None


@dataclass
class WorkflowProgress:
    """Audit trail of steps taken this call + pending-consent state."""
    steps_taken: list[dict] = field(default_factory=list)
    pending_consent_team: Optional[str] = None   # set when requires_consent=True
    pending_consent_step: Optional[str] = None   # which step is waiting for answer


class WorkflowRunner:
    """
    Stateless resolver that translates (step_name, result_key) pairs into
    structured StepOutcome objects using the STEP_TRANSITIONS lookup table.

    Usage in a wrapper:
        runner = WorkflowRunner(session)
        outcome = runner.advance("verify_otp", result.get("fast_response_key"))
        return outcome.message
    """

    def __init__(self, session: Any) -> None:
        self._session = session
        if session.workflow is None:
            session.workflow = WorkflowProgress()

    @property
    def progress(self) -> WorkflowProgress:
        return self._session.workflow  # type: ignore[return-value]

    def advance(
        self,
        step_name: str,
        result_key: str,
        extras: dict | None = None,
    ) -> StepOutcome:
        """
        Resolve (step_name, result_key) → StepOutcome.
        Records the step in WorkflowProgress.steps_taken for auditability.
        Sets pending_consent_* fields when the outcome requires user consent.
        """
        from workflow.definitions import STEP_TRANSITIONS

        ts = datetime.now(timezone.utc).isoformat()
        entry: dict = {"step": step_name, "key": result_key, "ts": ts}
        if extras:
            entry.update(extras)
        self.progress.steps_taken.append(entry)

        transition = STEP_TRANSITIONS.get(step_name, {}).get(result_key)

        if transition is None:
            return StepOutcome(
                message=(
                    f"Unexpected result '{result_key}' from {step_name}. "
                    "Acknowledge the issue and offer to help in another way."
                ),
            )

        if transition.requires_consent:
            self.progress.pending_consent_team = transition.escalation_team
            self.progress.pending_consent_step = step_name

        return StepOutcome(
            message=transition.message,
            requires_consent=transition.requires_consent,
            is_terminal=transition.is_terminal,
            escalation_team=transition.escalation_team,
        )
