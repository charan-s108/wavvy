from dataclasses import dataclass
from typing import Optional

from session.call_session import get_session


FORBIDDEN_ACTIONS: dict[str, list[str]] = {
    "voice_agent": [
        "delete_customer",
        "access_other_customer",
        "view_all_calls",
        "generate_refund",
    ],
    "companion_agent": [
        "execute_crm_write",
        "call_any_tool",
    ],
    "qa_agent": [
        "modify_transcript",
        "change_eval_score",
    ],
}


@dataclass
class ScopeResult:
    allowed: bool
    reason: str = ""
    inject_message: Optional[str] = None


def check_forbidden_actions(agent_type: str, tool_name: str) -> ScopeResult:
    forbidden = FORBIDDEN_ACTIONS.get(agent_type, [])
    if tool_name in forbidden:
        return ScopeResult(
            allowed=False,
            reason=f"Tool '{tool_name}' is forbidden for agent type '{agent_type}'",
            inject_message="I'm not able to perform that action.",
        )
    return ScopeResult(allowed=True)
