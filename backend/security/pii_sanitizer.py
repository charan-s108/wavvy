"""
PII sanitization — strip/mask sensitive customer fields before injecting
into LLM context. Raw DB objects must NEVER reach the LLM.
"""
import re


def _mask_email(email: str) -> str:
    if not email or "@" not in email:
        return "***"
    local, domain = email.split("@", 1)
    return f"{local[:2]}***@{domain}"


def _mask_phone(phone: str) -> str:
    digits = re.sub(r"[^\d]", "", phone or "")
    return f"***{digits[-3:]}" if len(digits) >= 3 else "***"


def sanitize_customer_context(customer: dict) -> dict:
    """
    Returns a safe subset of customer data for the LLM context.
    Includes enough for personalization without exposing raw PII.
    """
    transactions = customer.get("transactions") or []
    last_txn = transactions[0] if transactions else {}
    return {
        "first_name": (customer.get("name") or "").split()[0] if customer.get("name") else "there",
        "account_type": customer.get("account_type", "standard"),
        "account_status": customer.get("account_status", "active"),
        "kyc_status": customer.get("kyc_status", "pending"),
        "email_hint": _mask_email(customer.get("email", "")),
        "phone_hint": _mask_phone(customer.get("phone", "")),
        "txn_count": len(transactions),
        "last_txn_number": last_txn.get("txn_number"),
        "last_txn_status": last_txn.get("status"),
        "last_txn_merchant": last_txn.get("merchant"),
    }


def sanitize_tool_result(tool_name: str, result: dict) -> dict:
    """Strip internal/sensitive fields before adding a tool result to context."""
    BLOCKED = {"id", "customer_id", "address", "code", "token",
               "secret", "password", "auth_token", "handoff_bundle"}
    return {k: v for k, v in result.items() if k not in BLOCKED}
