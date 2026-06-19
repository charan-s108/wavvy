"""
Tool catalog — all available tool definitions keyed by name.
Active tools per call are selected at runtime from tenant config (tool_configs JSONB).
"""

TOOL_CATALOG: dict[str, dict] = {
    # ── Fin support tools ─────────────────────────────────────────────────────
    "verify_account": {
        "type": "function",
        "function": {
            "name": "verify_account",
            "description": (
                "Verify the caller's identity by looking up their account using phone number. "
                "Call once per session at the start of any support interaction. "
                "Required before using lookup_transaction."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "phone": {
                        "type": "string",
                        "description": "Caller's phone number (with or without country code)",
                    },
                },
                "required": ["phone"],
            },
        },
    },
    "lookup_transaction": {
        "type": "function",
        "function": {
            "name": "lookup_transaction",
            "description": (
                "Look up a specific transaction by ID from the verified customer's account. "
                "Requires verify_account to have been called first in this session."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "transaction_id": {
                        "type": "string",
                        "description": "Transaction ID to look up (e.g. TXN-7731)",
                    },
                },
                "required": ["transaction_id"],
            },
        },
    },
    # ── Shared ────────────────────────────────────────────────────────────────
    "escalate_to_human": {
        "type": "function",
        "function": {
            "name": "escalate_to_human",
            "description": (
                "Transfer the call to a human agent. Use when the customer requests it, "
                "fraud is suspected, a dispute needs manual review, "
                "or the AI cannot resolve the issue."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "enum": [
                            "customer_request",
                            "fraud_suspected",
                            "dispute_review",
                            "kyc_issue",
                            "unresolvable_issue",
                            "enterprise_pricing",
                            "complex_issue",
                            "low_sentiment",
                        ],
                        "description": "Reason for escalation",
                    },
                    "transcript_summary": {
                        "type": "string",
                        "description": "Brief summary of what was discussed and the issue status",
                    },
                },
                "required": ["reason", "transcript_summary"],
            },
        },
    },
}


def get_tool_definitions(tool_configs: dict) -> list[dict]:
    """Return tool definitions for tools enabled in tenant config."""
    return [
        TOOL_CATALOG[name]
        for name, cfg in tool_configs.items()
        if cfg.get("enabled", True) and name in TOOL_CATALOG
    ]


# Tool names as a set for fast membership checks
TOOL_NAMES: set[str] = set(TOOL_CATALOG.keys())
