"""
Safe tool execution wrapper with retry, timeout, idempotency, and structured error handling.
execute_with_recovery() is the ONLY entry point for tool execution in the pipeline.
Never exposes stack traces, SQL errors, or permission errors to the customer.
"""
from __future__ import annotations
import asyncio
import hashlib
import json
import logging
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any

from tools.wavvy_tools import execute_tool

logger = logging.getLogger(__name__)


# ── Structured types ──────────────────────────────────────────────────────────

class InternalErrorCode(str, Enum):
    TOOL_TIMEOUT    = "tool_timeout"
    TOOL_VALIDATION = "tool_validation"
    AUTH_FAILED     = "auth_failed"
    KB_FAILURE      = "kb_failure"
    UNKNOWN         = "unknown"


@dataclass
class ToolResult:
    success: bool
    fast_response_key: str | None = None
    template_vars: dict = field(default_factory=dict)
    data: dict = field(default_factory=dict)
    should_escalate: bool = False
    error_type: InternalErrorCode | None = None
    turn_id: int | None = None   # set by execute_with_recovery; Workflow Engine validates


# ── Per-tool retry policies ───────────────────────────────────────────────────

RETRY_POLICY: dict[str, int] = {
    "escalate_to_human":  1,   # idempotent — single retry
    "default":            1,
}

# ── Per-tool timeout budgets (seconds) ────────────────────────────────────────

TOOL_TIMEOUTS: dict[str, float] = {
    "escalate_to_human":  3.0,
    "default":            2.0,
}

# ── Idempotency key ───────────────────────────────────────────────────────────

def make_idempotency_key(call_id: str, tool_name: str, args: dict, step_id: str) -> str:
    normalized = json.dumps({k: args[k] for k in sorted(args)}, sort_keys=True)
    payload = f"{call_id}:{tool_name}:{step_id}:{normalized}"
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


IDEMPOTENCY_TTL_SECONDS = 600  # 10 minutes


def _check_idempotency(session, ikey: str) -> ToolResult | None:
    """Returns cached ToolResult if key exists and not expired, else None."""
    entry = session._idempotency_store.get(ikey)
    if not entry:
        return None
    result, expires_at = entry
    if datetime.now(timezone.utc) > expires_at:
        del session._idempotency_store[ikey]
        return None
    return result


def _store_idempotency(session, ikey: str, result: ToolResult) -> None:
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=IDEMPOTENCY_TTL_SECONDS)
    session._idempotency_store[ikey] = (result, expires_at)

    # Prune expired entries
    now = datetime.now(timezone.utc)
    expired = [k for k, (_, exp) in session._idempotency_store.items() if now > exp]
    for k in expired:
        del session._idempotency_store[k]


# ── execute_with_recovery ─────────────────────────────────────────────────────

async def execute_with_recovery(
    tool_name: str,
    args: dict,
    call_id: str,
    turn_id: int,
    step_id: str = "unknown",
    session=None,
) -> ToolResult:
    """
    Safe tool execution wrapper:
    1. Checks idempotency store — returns cached result if present
    2. Retries transiently failing tools (tool-specific retry count)
    3. Enforces per-tool timeout via asyncio.wait_for
    4. Classifies all exceptions into InternalErrorCode — never exposes internals
    5. Injects turn_id into ToolResult before returning
    6. Stores successful result in idempotency store
    """
    from session.call_session import get_session

    if session is None:
        session = get_session(call_id)

    # Track last tool attempted
    if session:
        session._last_tool_attempted = tool_name
        session._tool_last_called[tool_name] = datetime.now(timezone.utc)

    # Idempotency check
    ikey = make_idempotency_key(call_id, tool_name, args, step_id)
    if session:
        cached = _check_idempotency(session, ikey)
        if cached:
            logger.info(f"[{call_id}] Idempotency hit: {tool_name} key={ikey}")
            cached.turn_id = turn_id
            return cached

    retries = RETRY_POLICY.get(tool_name, RETRY_POLICY["default"])
    timeout = TOOL_TIMEOUTS.get(tool_name, TOOL_TIMEOUTS["default"])

    last_error: InternalErrorCode = InternalErrorCode.UNKNOWN

    for attempt in range(retries + 1):
        try:
            raw = await asyncio.wait_for(
                execute_tool(tool_name, args, call_id),
                timeout=timeout,
            )
            result = ToolResult(
                success=raw.get("success", True),
                fast_response_key=raw.get("fast_response_key"),
                template_vars=raw.get("template_vars", {}),
                data={k: v for k, v in raw.items()
                      if k not in ("success", "fast_response_key", "template_vars")},
                turn_id=turn_id,
            )
            # Cache successful result
            if session and result.success:
                _store_idempotency(session, ikey, result)
            return result

        except asyncio.TimeoutError:
            last_error = InternalErrorCode.TOOL_TIMEOUT
            logger.error(json.dumps({
                "call_id": call_id, "tool": tool_name, "attempt": attempt + 1,
                "error_type": last_error, "detail": f"timeout>{timeout}s",
            }))
            # Timeout is not retryable — break immediately
            break

        except (ValueError, TypeError) as exc:
            last_error = InternalErrorCode.TOOL_VALIDATION
            logger.error(json.dumps({
                "call_id": call_id, "tool": tool_name, "attempt": attempt + 1,
                "error_type": last_error, "detail": type(exc).__name__,
            }))
            break  # validation errors are not retryable

        except PermissionError as exc:
            last_error = InternalErrorCode.AUTH_FAILED
            logger.error(json.dumps({
                "call_id": call_id, "tool": tool_name, "attempt": attempt + 1,
                "error_type": last_error, "detail": type(exc).__name__,
            }))
            break  # auth errors are not retryable

        except Exception as exc:
            last_error = InternalErrorCode.UNKNOWN
            # Log full traceback so the failing line is always visible in logs
            logger.exception(
                "[%s] %s attempt %d/%d failed: %s",
                call_id, tool_name, attempt + 1, retries + 1, exc,
            )
            if attempt < retries:
                # Exponential backoff with jitter
                delay = (0.05 * (2 ** attempt)) + random.uniform(0, 0.05)
                await asyncio.sleep(delay)

    return ToolResult(
        success=False,
        fast_response_key="tool_error",
        should_escalate=False,
        error_type=last_error,
        turn_id=turn_id,
    )
