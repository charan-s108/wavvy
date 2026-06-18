from session.conversation_state import ConversationStage

# Maps each workflow stage to the set of tools permitted at that point.
# The LLM never decides permissions — this is server-authoritative.
#
# Wavvy demo tools: capture_lead, schedule_demo
# Fin fintech tools (read): verify_account, send_otp, verify_otp, lookup_transaction,
#                    search_transactions, check_payment_status,
#                    get_account_holds, get_refund_status, get_dispute_status
# Fin fintech tools (write): unlock_account, initiate_refund, raise_dispute, report_fraud
# Always available: escalate_to_human only
# cancel_escalation is stage-scoped (TOOL_EXECUTION, ESCALATION) — not always-on

_FIN_READ_TOOLS = {
    "verify_account", "send_otp", "verify_otp",
    "lookup_transaction", "search_transactions", "check_payment_status",
    "get_account_holds", "get_refund_status", "get_dispute_status",
}

_FIN_WRITE_TOOLS = {
    "unlock_account", "initiate_refund", "raise_dispute", "report_fraud",
}

TOOL_PERMISSIONS: dict[ConversationStage, set[str]] = {
    ConversationStage.GREETING: {
        "capture_lead", "verify_account", "escalate_to_human",
    },
    ConversationStage.DISCOVERY: {
        "capture_lead", "verify_account", "escalate_to_human",
    },
    ConversationStage.VERIFICATION: {
        "capture_lead", "schedule_demo",
        *_FIN_READ_TOOLS,
        "escalate_to_human",
    },
    ConversationStage.TOOL_EXECUTION: {
        "capture_lead", "schedule_demo",
        *_FIN_READ_TOOLS,
        *_FIN_WRITE_TOOLS,
        "escalate_to_human", "cancel_escalation",
    },
    ConversationStage.ESCALATION: {
        "escalate_to_human", "cancel_escalation",
    },
    ConversationStage.RESOLUTION: {
        "escalate_to_human",
    },
    ConversationStage.ENDED: set(),
}


def is_tool_allowed(
    stage: ConversationStage,
    tool_name: str,
    escalated: bool = False,
    session=None,
) -> tuple[bool, str]:
    """Returns (allowed, reason). Called before every tool execution.

    When session.orchestrator_state.mode == WORKFLOW, permissions are read from
    the active node's allowed_tools list (node-scoped).  For GENERAL mode and
    the legacy fintech workflow the static TOOL_PERMISSIONS table is used.
    """
    if escalated and tool_name != "escalate_to_human":
        return False, "Session is escalated — only escalate_to_human is permitted"

    # Orchestrator-aware path: delegate to node when in WORKFLOW mode
    if session is not None:
        try:
            from session.orchestrator_state import ExecutionMode
            state = session.orchestrator_state
            if state.mode == ExecutionMode.ESCALATION:
                if tool_name == "escalate_to_human":
                    return True, ""
                return False, "Only escalate_to_human permitted in ESCALATION mode"
            if state.mode == ExecutionMode.WORKFLOW and state.active_workflow_id:
                from workflow.engine import load_node
                node = load_node(state.active_workflow_id, state.active_node_id or "")
                if node is not None:
                    if tool_name in node.allowed_tools or tool_name == "escalate_to_human":
                        return True, ""
                    return False, (
                        f"Tool '{tool_name}' not in node '{node.name}' allowed_tools"
                    )
        except Exception:
            pass  # fall through to static table on any error

    # Static table (GENERAL mode + legacy fintech workflow)
    allowed = TOOL_PERMISSIONS.get(stage, set())
    if tool_name in allowed:
        return True, ""
    return False, (
        f"Tool '{tool_name}' is not permitted in stage '{stage.value}'."
    )
