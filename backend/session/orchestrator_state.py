"""
OrchestratorState — top-level call lifetime state for the Wavvy orchestrator.

ExecutionMode is the primary abstraction. Every call starts in GENERAL.
The orchestrator transitions to WORKFLOW when a customer utterance matches an
active workflow's intent. ESCALATION is terminal.

FAQ is NOT a mode — it is a capability invoked from any mode. A FAQ answer is
injected into the current turn's context without changing the execution mode.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ExecutionMode(Enum):
    GENERAL    = "general"     # default; open-ended LLM; conversational tools only
    WORKFLOW   = "workflow"    # active node graph; per-node scoped tools; slot monitor
    ESCALATION = "escalation"  # terminal; human handoff in progress


@dataclass
class EntitySlots:
    """Accumulated structured entities extracted from STT utterances.

    Phone and OTP are accumulated across multiple turns — a customer may say
    digits slowly or across two STT chunks. The extractor appends digits until
    a complete value is available.
    """
    phone:  Optional[str] = None   # accumulated phone digits; set when >= 10 digits
    otp:    Optional[str] = None   # 6-digit OTP code; set when exactly 6 digits found
    txn_id: Optional[str] = None   # TXN-XXXX; set on first match

    def clear_phone(self) -> None:
        self.phone = None

    def clear_otp(self) -> None:
        self.otp = None

    def clear_txn_id(self) -> None:
        self.txn_id = None


@dataclass
class OrchestratorState:
    """Per-call orchestrator state.

    Stored on CallSession alongside the existing conv_state (ConversationStateManager).
    conv_state remains the within-workflow stage tracker for the default fintech
    workflow only. OrchestratorState owns the top-level mode and node position.
    """
    mode: ExecutionMode = ExecutionMode.GENERAL

    # Active workflow fields — all None unless mode == WORKFLOW
    active_workflow_id: Optional[str] = None   # workflow_definitions.id
    active_node_id:     Optional[str] = None   # WorkflowNode.id within active workflow
    node_variables:     dict          = field(default_factory=dict)   # collected slot values
    node_attempts:      int           = 0      # attempts at current node (for max_attempts check)

    # Entity accumulation — populated by entity_extractor on every utterance
    entity_slots: EntitySlots = field(default_factory=EntitySlots)

    # FAQ dedup — prevents re-injecting the same RAG chunk two turns in a row
    last_faq_chunk_id: Optional[str] = None

    # Escalation confirmation gate — set when escalation intent first detected.
    # escalate_to_human is only offered to the LLM AFTER the customer explicitly
    # confirms.  This prevents the agent from transferring calls without consent.
    escalation_pending: bool = False

    # Name collection gate — set alongside escalation_pending when the customer has
    # NOT been session-verified.  The next non-negative response is treated as the
    # customer's name and immediately triggers escalation.  Skipped when
    # session_verified is True (we already know who they are).
    escalation_needs_name: bool = False

    # Name collected during pre-escalation identity check.  Set when the customer
    # responds to "Could you share your name?" before an unverified transfer.
    # Used by build_escalation_packet() to populate lead.name in the handoff bundle.
    escalation_caller_name: str = ""

    # Reason collection gate — set after name is collected.  The next customer turn
    # is treated as the call reason (payment, fraud, account access, general).
    escalation_needs_reason: bool = False

    # Human-readable call reason collected during pre-escalation (e.g. "Payment Issue").
    # Used as bundle.reason in the handoff so the agent console shows it immediately.
    escalation_call_reason: str = ""

    # LLM-action node advancement: when the LLM calls a tool at an action node
    # (auto_actions=[]), the tool's fast_response_key is stored here so the next
    # llm_node() call's advance() can evaluate the edge and move to the next node.
    # Tuple: (tool_name, fast_response_key).  Cleared after edge evaluation.
    pending_tool_result: Optional[tuple[str, str]] = None

    # Session-level identity verification flag.
    # Set to True after verify_otp succeeds for the first time in this call.
    # All subsequent workflows skip collect_phone → send_otp → verify_otp and
    # enter at the first post-verification node directly.
    session_verified: bool = False

    # Workflows completed this call — used to prevent the issue classifier from
    # re-entering a workflow that already ran to completion.
    completed_workflow_ids: set = field(default_factory=set)

    # Terminal tools that returned success this call (e.g. "initiate_refund",
    # "unlock_account").  Used to suppress cross-workflow pivots when the goal
    # is already achieved, even if exit_workflow() was never called (LLM tool path).
    completed_terminal_tools: set = field(default_factory=set)

    def enter_workflow(self, workflow_id: str, entry_node_id: str) -> None:
        self.mode               = ExecutionMode.WORKFLOW
        self.active_workflow_id = workflow_id
        self.active_node_id     = entry_node_id
        self.node_variables     = {}
        self.node_attempts      = 0

    def advance_to_node(self, node_id: str) -> None:
        """Move to the next node within the same workflow."""
        self.active_node_id = node_id
        self.node_variables  = {}
        self.node_attempts   = 0

    def exit_workflow(self) -> None:
        """Workflow completed (success or terminal failure) — return to GENERAL.

        Clears entity slots so a subsequent issue-classifier match for the same
        workflow can't skip the identity-collection steps by reusing the old phone.
        Records the workflow ID so the classifier won't re-enter it this call.
        """
        if self.active_workflow_id:
            self.completed_workflow_ids.add(self.active_workflow_id)
        self.mode               = ExecutionMode.GENERAL
        self.active_workflow_id = None
        self.active_node_id     = None
        self.node_variables     = {}
        self.node_attempts      = 0
        # Clear all entity slots — prevents the next turn from auto-firing
        # verify_account / verify_otp with stale values from the finished workflow.
        self.entity_slots.clear_phone()
        self.entity_slots.clear_otp()
        self.entity_slots.clear_txn_id()

    def enter_escalation(self) -> None:
        self.mode = ExecutionMode.ESCALATION

    def is_in_workflow(self) -> bool:
        return self.mode == ExecutionMode.WORKFLOW

    def is_escalating(self) -> bool:
        return self.mode == ExecutionMode.ESCALATION
