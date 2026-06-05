from guardrails.tool_permissions import is_tool_allowed
from guardrails.validator import validate_tool_args, ValidationResult
from guardrails.auth_gate import check_action_authorized, GuardrailResult
from guardrails.scope import check_forbidden_actions, ScopeResult
from guardrails.rate_limiter import check_rate_limits, increment_tool_call, increment_turn, RateLimitResult
from dataclasses import dataclass
from typing import Optional


@dataclass
class PipelineResult:
    allowed: bool
    stage: str = ""
    reason: str = ""
    inject_message: Optional[str] = None
    action: Optional[str] = None


def run_guardrail_pipeline(
    call_id: str,
    tool_name: str,
    tool_args: dict,
    agent_type: str = "voice_agent",
) -> PipelineResult:
    # Stage 1 — format + type validation
    v = validate_tool_args(tool_name, tool_args)
    if not v.valid:
        return PipelineResult(allowed=False, stage="validator", reason=v.error)

    # Stage 2 — auth state gate
    a = check_action_authorized(call_id, tool_name)
    if not a.allowed:
        return PipelineResult(
            allowed=False, stage="auth",
            reason=a.reason, inject_message=a.inject_message,
        )

    # Stage 3 — scope boundary
    s = check_forbidden_actions(agent_type, tool_name)
    if not s.allowed:
        return PipelineResult(
            allowed=False, stage="scope",
            reason=s.reason, inject_message=s.inject_message,
        )

    # Stage 4 — rate limits
    r = check_rate_limits(call_id)
    if not r.allowed:
        return PipelineResult(
            allowed=False, stage="rate",
            reason=r.reason, action=r.action,
        )

    increment_tool_call(call_id)
    return PipelineResult(allowed=True)
