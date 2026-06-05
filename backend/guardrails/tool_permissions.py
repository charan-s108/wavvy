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
) -> tuple[bool, str]:
    """Returns (allowed, reason). Called before every tool execution."""
    if escalated and tool_name != "escalate_to_human":
        return False, "Session is escalated — only escalate_to_human is permitted"
    allowed = TOOL_PERMISSIONS.get(stage, set())
    if tool_name in allowed:
        return True, ""
    return False, (
        f"Tool '{tool_name}' is not permitted in stage '{stage.value}'."
    )
