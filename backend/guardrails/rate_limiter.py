from dataclasses import dataclass
from typing import Optional

from session.call_session import get_session


MAX_TURNS_PER_CALL = 30
MAX_TOOL_CALLS_PER_TURN = 3
MAX_TOKENS_PER_CALL = 50_000


@dataclass
class RateLimitResult:
    allowed: bool
    reason: str = ""
    action: Optional[str] = None


def check_rate_limits(call_id: str) -> RateLimitResult:
    session = get_session(call_id)
    if not session:
        return RateLimitResult(allowed=False, reason="No active session", action="force_end_call")

    if session.turn_count >= MAX_TURNS_PER_CALL:
        return RateLimitResult(
            allowed=False,
            reason=f"Call exceeded maximum turn limit ({MAX_TURNS_PER_CALL})",
            action="force_end_call",
        )

    if session.tool_calls_this_turn >= MAX_TOOL_CALLS_PER_TURN:
        return RateLimitResult(
            allowed=False,
            reason=f"Too many tool calls in a single turn ({MAX_TOOL_CALLS_PER_TURN} max)",
        )

    if session.cumulative_tokens >= MAX_TOKENS_PER_CALL:
        return RateLimitResult(
            allowed=False,
            reason=f"Call exceeded token budget ({MAX_TOKENS_PER_CALL})",
            action="force_end_call",
        )

    return RateLimitResult(allowed=True)


def increment_tool_call(call_id: str) -> None:
    session = get_session(call_id)
    if session:
        session.tool_calls_this_turn += 1


def increment_turn(call_id: str, tokens_used: int = 0) -> None:
    session = get_session(call_id)
    if session:
        session.turn_count += 1
        session.tool_calls_this_turn = 0
        session.cumulative_tokens += tokens_used
