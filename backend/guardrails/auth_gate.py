from dataclasses import dataclass
from typing import Optional

from session.auth_state import AuthState
from session.call_session import get_session


PROTECTED_TOOLS = {"update_record", "confirm_action", "crm_search"}


@dataclass
class GuardrailResult:
    allowed: bool
    reason: str = ""
    inject_message: Optional[str] = None
    action: Optional[str] = None


def check_action_authorized(call_id: str, tool_name: str) -> GuardrailResult:
    if tool_name not in PROTECTED_TOOLS:
        return GuardrailResult(allowed=True)

    session = get_session(call_id)
    if not session:
        return GuardrailResult(
            allowed=False,
            reason="No active session found for this call",
        )

    if session.auth_state.state != AuthState.VERIFIED:
        return GuardrailResult(
            allowed=False,
            reason=f"Authentication required before '{tool_name}'. "
                   f"Current auth state: {session.auth_state.state.value}",
            inject_message="I need to verify your identity first before making any changes. "
                           "Let me send a verification code to your registered phone.",
        )

    return GuardrailResult(allowed=True)
