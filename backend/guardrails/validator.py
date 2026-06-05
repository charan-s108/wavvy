import re
from dataclasses import dataclass


@dataclass
class ValidationResult:
    valid: bool
    error: str = ""


TOOL_VALIDATORS: dict[str, dict[str, any]] = {
    "lookup_account": {
        "identifier_type": lambda v: v in {"phone", "order_id"},
        "identifier": lambda v: len(str(v)) > 5,
    },
    "send_2fa": {
        "customer_id": lambda v: len(str(v)) > 0,
    },
    "verify_2fa": {
        "customer_id": lambda v: len(str(v)) > 0,
        "code": lambda v: re.match(r"^\d{6}$", str(v)) is not None,
    },
    "update_record": {
        "customer_id": lambda v: len(str(v)) > 0,
        "field": lambda v: v in {"address", "email", "phone", "account_type"},
        "value": lambda v: 0 < len(str(v)) < 500,
    },
    "confirm_action": {
        "customer_id": lambda v: len(str(v)) > 0,
        "action_type": lambda v: v in {"refund", "cancel_order", "update_plan", "close_ticket"},
        "action_summary": lambda v: len(str(v)) > 10,
    },
    "escalate_to_human": {
        "reason": lambda v: v in {"low_sentiment", "customer_request", "auth_failure", "complex_issue"},
        "transcript_summary": lambda v: len(str(v)) > 10,
    },
    "get_order_status": {
        "customer_id": lambda v: len(str(v)) > 0,
    },
    "get_call_history": {
        "customer_id": lambda v: len(str(v)) > 0,
    },
    "crm_search": {
        "query": lambda v: len(str(v)) > 0,
        "customer_id": lambda v: len(str(v)) > 0,
    },
}


def validate_tool_args(tool_name: str, args: dict) -> ValidationResult:
    validators = TOOL_VALIDATORS.get(tool_name, {})
    for field_name, validator in validators.items():
        if field_name in args:
            try:
                if not validator(args[field_name]):
                    return ValidationResult(
                        valid=False,
                        error=f"Invalid value for '{field_name}' in tool '{tool_name}'",
                    )
            except Exception:
                return ValidationResult(
                    valid=False,
                    error=f"Validation error for '{field_name}' in tool '{tool_name}'",
                )
    return ValidationResult(valid=True)
