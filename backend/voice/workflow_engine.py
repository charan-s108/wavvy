"""
Workflow Engine — single source of truth for session progression.

Rules:
- ALL WorkflowSession mutations happen inside async with session.workflow_lock
- Intent Router is used ONLY for initialization (first turn, no active workflow)
- Once a workflow is active, only the Workflow Engine advances steps
- TranscriptProcessor must contain NO hidden branching — add a WorkflowNode instead
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from voice.intent_router import Intent
from voice.deterministic_responses import WAVVY_DEMO


class WorkflowStepId(Enum):
    START         = "start"
    CAPTURE_LEAD  = "capture_lead"
    SCHEDULE_DEMO = "schedule_demo"
    ESCALATE      = "escalate"
    RESOLVED      = "resolved"


@dataclass
class WorkflowNode:
    id: WorkflowStepId
    kind: Literal["tool", "state"]     # "tool" → execute tool; "state" → speak + wait
    name: str                          # tool name OR state label
    on_success: WorkflowStepId | None = None
    on_failure: WorkflowStepId | None = None
    on_timeout: WorkflowStepId | None = None
    fast_response_key: str | None = None       # for kind="state": key to speak
    required_entities: list[str] = field(default_factory=list)


@dataclass
class PendingAction:
    tool: str
    args: dict
    expires_at: datetime
    idempotency_key: str
    created_turn_id: int   # discard confirmation from turns before this


@dataclass
class WorkflowSummary:
    """
    Structured state — converted to minimal text only at LLM context build time.
    LLM never sees raw session state; it sees only to_text().
    """
    lead_captured: bool = False
    demo_scheduled: bool = False
    escalated: bool = False
    last_action: str | None = None          # most recent completed action
    sentiment_status: str | None = None     # "positive" | "neutral" | "negative"
    recent_failure: str | None = None       # last tool failure key
    escalation_reason: str | None = None
    topics_discussed: list[str] = field(default_factory=list)
    last_slot_label: str | None = None      # short label of last booked/suggested slot

    def to_text(self) -> str:
        """Minimal structured context for LLM. Fields included only when non-default."""
        parts = []
        if self.lead_captured:
            parts.append("lead_captured")
        if self.demo_scheduled:
            parts.append("demo_scheduled")
        if self.escalated:
            parts.append("escalated")
        if self.last_action:
            parts.append(self.last_action)
        if self.recent_failure:
            parts.append(f"last_error={self.recent_failure}")
        if self.escalation_reason:
            parts.append(f"escalation={self.escalation_reason}")
        if self.topics_discussed:
            parts.append(f"topics={','.join(self.topics_discussed)}")
        return "; ".join(parts) if parts else "initial"

    def add_topic(self, topic: str) -> None:
        if topic not in self.topics_discussed:
            self.topics_discussed.append(topic)


@dataclass
class WorkflowSession:
    intent: Intent = Intent.UNKNOWN
    entities: dict = field(default_factory=dict)
    current_step: WorkflowStepId = WorkflowStepId.START
    completed_steps: list[WorkflowStepId] = field(default_factory=list)
    pending_action: PendingAction | None = None   # ONE active at a time
    summary: WorkflowSummary = field(default_factory=WorkflowSummary)
    call_mode: str = WAVVY_DEMO
    _consecutive_unknown_intents: int = 0
    _entity_ask_count: dict = field(default_factory=dict)  # entity → # times asked

    # Slot confirmation state
    pending_slot: dict | None = None                        # slot awaiting user confirmation
    pending_slot_expires_at: datetime | None = None         # UTC; None = no expiry set yet

    # Clarification tracking — escalate after MAX_CLARIFICATION_ATTEMPTS
    clarification_attempts: int = 0

    # Cancellation confirmation state
    pending_cancel: bool = False

    # Rescheduling mode — True while waiting for a new preferred_time after reschedule request
    is_rescheduling: bool = False

    # User's inferred timezone (ISO name, e.g. "Asia/Kolkata", "America/New_York")
    user_timezone: str = "Asia/Kolkata"

    # Clarification-before-escalation tracking for UNKNOWN intents
    # Reset to 0 on any non-UNKNOWN intent so counters don't bleed across topics.
    _unknown_clarification_count: int = 0   # how many clarification turns sent this streak
    _last_unknown_ts: float = 0.0           # monotonic time of the last UNKNOWN turn


# ── Workflow definitions ──────────────────────────────────────────────────────

S = WorkflowStepId   # alias for brevity

WORKFLOWS: dict[Intent, list[WorkflowNode]] = {

    # Pure KB + LLM — no tool execution needed
    Intent.PRODUCT_QA:         [],
    Intent.COMPETITOR_COMPARE: [],
    Intent.INTEGRATION_QA:     [],
    Intent.GENERAL_QA:         [],

    # Pricing: FAST_RESPONSE handles standard tiers immediately.
    # enterprise keyword detected → Workflow Engine transitions to ESCALATE.
    Intent.PRICING_INQUIRY: [],   # handled via FAST_RESPONSES in pipeline

    Intent.DEMO_REQUEST: [
        # Step 1: capture name + email (ask one at a time until both present)
        WorkflowNode(
            id=S.CAPTURE_LEAD,
            kind="tool",
            name="capture_lead",
            required_entities=["name", "email"],
            on_success=S.SCHEDULE_DEMO,
            on_failure=S.ESCALATE,
        ),
        # Step 2: collect preferred_day then preferred_time before scheduling.
        # Two-question flow: ask for day first, then time on that day.
        # Only calls schedule_demo tool once BOTH entities are present.
        WorkflowNode(
            id=S.SCHEDULE_DEMO,
            kind="state",
            name="ask_demo_day",
            fast_response_key="ask_demo_day",
            required_entities=["preferred_day", "preferred_time"],
            on_success=S.RESOLVED,
            on_failure=S.ESCALATE,
            on_timeout=S.RESOLVED,
        ),
    ],

    Intent.HUMAN_AGENT: [
        # Capture at least a name before escalating (for agent context)
        WorkflowNode(
            id=S.CAPTURE_LEAD,
            kind="tool",
            name="capture_lead",
            required_entities=["name"],
            on_success=S.ESCALATE,
            on_failure=S.ESCALATE,
        ),
        WorkflowNode(
            id=S.ESCALATE,
            kind="tool",
            name="escalate_to_human",
            on_success=S.RESOLVED,
            on_failure=S.RESOLVED,
        ),
    ],

    # After 3 consecutive UNKNOWNs (or 2 + negative sentiment), escalate
    Intent.UNKNOWN: [
        WorkflowNode(
            id=S.ESCALATE,
            kind="tool",
            name="escalate_to_human",
            on_success=S.RESOLVED,
            on_failure=S.RESOLVED,
        ),
    ],
}


def get_workflow(intent: Intent) -> list[WorkflowNode]:
    """Returns the workflow node list for the given intent."""
    return WORKFLOWS.get(intent, [])


def get_current_node(workflow: WorkflowSession) -> WorkflowNode | None:
    """Returns the active WorkflowNode for the given step, or None if no tool steps."""
    nodes = get_workflow(workflow.intent)
    for node in nodes:
        if node.id == workflow.current_step:
            return node
    return None


def missing_entities(node: WorkflowNode, entities: dict) -> list[str]:
    """Returns list of required entity keys not yet present in entities."""
    return [e for e in node.required_entities if not entities.get(e)]


def advance_step(workflow: WorkflowSession, outcome: Literal["success", "failure", "timeout"]) -> WorkflowStepId:
    """
    Transitions current_step based on outcome.
    Returns the new step id.
    Caller must hold session.workflow_lock.
    """
    node = get_current_node(workflow)
    if not node:
        return WorkflowStepId.RESOLVED

    if workflow.current_step not in workflow.completed_steps:
        workflow.completed_steps.append(workflow.current_step)

    if outcome == "success":
        next_step = node.on_success or WorkflowStepId.RESOLVED
    elif outcome == "timeout":
        next_step = node.on_timeout or WorkflowStepId.RESOLVED
    else:
        next_step = node.on_failure or WorkflowStepId.ESCALATE

    workflow.current_step = next_step
    return next_step


def is_workflow_active(workflow: WorkflowSession) -> bool:
    """True if a workflow has been initialized and is not yet resolved/escalated."""
    return (
        workflow.current_step not in (WorkflowStepId.START, WorkflowStepId.RESOLVED)
        and workflow.intent != Intent.UNKNOWN
    )


def next_missing_entity_prompt(node: WorkflowNode, entities: dict) -> str | None:
    """
    Returns the FAST_RESPONSE key to prompt for the next missing required entity.
    Returns None if all required entities are present.
    """
    missing = missing_entities(node, entities)
    if not missing:
        return None
    # Map entity name → prompt key
    prompts = {
        "name":           "ask_name",
        "email":          "ask_email",
        "phone":          "ask_phone",
        "company":        "ask_company",
        "preferred_day":  "ask_demo_day",
        "preferred_time": "ask_demo_time",
    }
    return prompts.get(missing[0])
