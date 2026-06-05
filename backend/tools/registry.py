"""
Tool catalog — all available tool definitions keyed by name.
Active tools per call are selected at runtime from tenant config (tool_configs JSONB).
"""

TOOL_CATALOG: dict[str, dict] = {
    # ── Wavvy self-demo tools ─────────────────────────────────────────────────
    "capture_lead": {
        "type": "function",
        "function": {
            "name": "capture_lead",
            "description": (
                "Save a prospect's contact details (name, email, phone, company) "
                "to the leads database. Call this when the user wants to schedule a "
                "demo or talk to the team. Ask for one field at a time."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Full name of the prospect",
                    },
                    "email": {
                        "type": "string",
                        "description": "Email address of the prospect",
                    },
                    "phone": {
                        "type": "string",
                        "description": "Phone number of the prospect",
                    },
                    "company": {
                        "type": "string",
                        "description": "Company the prospect works at",
                    },
                    "intent": {
                        "type": "string",
                        "description": "What they called about (e.g. demo_request, human_agent)",
                    },
                },
                "required": ["name", "intent"],
            },
        },
    },
    "schedule_demo": {
        "type": "function",
        "function": {
            "name": "schedule_demo",
            "description": (
                "Book a demo appointment for a prospect. Call after capture_lead "
                "has run and the prospect has provided a preferred time."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "lead_id": {
                        "type": "string",
                        "description": "Lead UUID from capture_lead (optional — creates lead if missing)",
                    },
                    "name": {
                        "type": "string",
                        "description": "Prospect's name",
                    },
                    "email": {
                        "type": "string",
                        "description": "Prospect's email for confirmation",
                    },
                    "preferred_time": {
                        "type": "string",
                        "description": "Natural language time preference (e.g. 'Tuesday afternoon')",
                    },
                },
                "required": ["name", "preferred_time"],
            },
        },
    },
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
