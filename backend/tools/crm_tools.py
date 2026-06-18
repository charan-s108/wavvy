"""
CRM tool implementations. All async. Called only after the guardrail pipeline passes.
2FA is enforced via the TwoFactorState state machine — never by prompt.
"""
import json
import re
import random
import logging
from datetime import datetime, timezone

from sqlalchemy import text

from database import AsyncSessionLocal
from session.call_session import get_session, ACTIVE_CALLS
from session.auth_state import AuthState

logger = logging.getLogger(__name__)


# ── lookup_account ──────────────────────────────────────────────────────────

def _normalize_phone(raw: str) -> str:
    """Strip everything except digits and leading +."""
    digits = re.sub(r"[^\d]", "", raw)
    return digits


async def lookup_account(identifier: str, identifier_type: str, call_id: str) -> dict:
    async with AsyncSessionLocal() as db:
        if identifier_type == "phone":
            digits = _normalize_phone(identifier)
            result = await db.execute(
                text("""
                    SELECT id, name, phone, account_type, email,
                           account_status, kyc_status, fraud_hold_active
                    FROM customers
                    WHERE regexp_replace(phone, '[^0-9]', '', 'g') = :v
                """),
                {"v": digits},
            )
            row = result.mappings().first()
            if not row and len(digits) >= 7:
                result = await db.execute(
                    text("""
                        SELECT id, name, phone, account_type, email,
                               account_status, kyc_status, fraud_hold_active
                        FROM customers
                        WHERE regexp_replace(phone, '[^0-9]', '', 'g') LIKE :suffix
                    """),
                    {"suffix": f"%{digits}"},
                )
                row = result.mappings().first()
        else:
            # txn_number lookup via transactions table
            result = await db.execute(
                text("""
                    SELECT c.id, c.name, c.phone, c.account_type, c.email,
                           c.account_status, c.kyc_status, c.fraud_hold_active
                    FROM customers c
                    JOIN transactions t ON t.customer_id = c.id
                    WHERE t.txn_number = :txn
                """),
                {"txn": identifier.upper()},
            )
            row = result.mappings().first()

    if not row:
        return {"found": False, "message": f"No account found for {identifier}"}

    session = get_session(call_id)
    if session:
        session.customer_id = str(row["id"])
        if hasattr(session, "auth_state"):
            session.auth_state.customer_id = str(row["id"])

    return {
        "found": True,
        "customer_id":    str(row["id"]),
        "name":           row["name"],
        "phone":          row["phone"],
        "account_type":   row["account_type"],
        "email":          row["email"],
        "account_status": row["account_status"],
        "kyc_status":     row["kyc_status"],
        "fraud_hold_active": row["fraud_hold_active"],
    }


# ── send_2fa ────────────────────────────────────────────────────────────────

async def send_2fa(customer_id: str, call_id: str) -> dict:
    session = get_session(call_id)
    if not session:
        return {"sent": False, "error": "No active session"}

    if not session.auth_state.can_send():
        return {
            "sent": False,
            "error": f"Cannot send code in state: {session.auth_state.state.value}",
        }

    code = str(random.randint(100000, 999999))
    session.auth_state.mark_sent(code, customer_id)

    logger.info(f"[DEMO] 2FA code for customer {customer_id} on call {call_id}: {code}")

    return {
        "sent": True,
        "message": "Verification code sent to your registered phone number. It expires in 5 minutes.",
        "expires_minutes": 5,
    }


# ── verify_2fa ──────────────────────────────────────────────────────────────

async def verify_2fa(customer_id: str, code: str, call_id: str) -> dict:
    session = get_session(call_id)
    if not session:
        return {"verified": False, "error": "No active session"}

    auth = session.auth_state

    if auth.is_expired():
        return {
            "verified": False,
            "error": "Verification code has expired. Please request a new one.",
            "expired": True,
        }

    if not auth.can_verify():
        return {
            "verified": False,
            "error": f"Cannot verify in current state: {auth.state.value}",
        }

    success = auth.attempt_verify(code)

    if success:
        return {"verified": True, "message": "Identity verified successfully."}

    if auth.state == AuthState.FAILED:
        return {
            "verified": False,
            "error": "Maximum verification attempts reached. Escalating to a human agent.",
            "max_attempts_reached": True,
        }

    remaining = auth.max_attempts - auth.attempts
    return {
        "verified": False,
        "error": f"Incorrect code. {remaining} attempt{'s' if remaining != 1 else ''} remaining.",
    }


# ── update_record ───────────────────────────────────────────────────────────

async def update_record(customer_id: str, field: str, value: str, call_id: str) -> dict:
    async with AsyncSessionLocal() as db:
        await db.execute(
            text(f"UPDATE customers SET {field} = :v, updated_at = NOW() WHERE id = :id"),
            {"v": value, "id": customer_id},
        )
        await db.commit()

    logger.info(f"[{call_id}] Updated {field} for customer {customer_id}")
    return {
        "updated": True,
        "field": field,
        "new_value": value,
        "message": f"Your {field} has been updated successfully.",
    }


# ── confirm_action ──────────────────────────────────────────────────────────

async def confirm_action(
    customer_id: str, action_type: str, action_summary: str, call_id: str
) -> dict:
    async with AsyncSessionLocal() as db:
        # Mark the call's crm_updated flag
        await db.execute(
            text("UPDATE calls SET crm_updated = TRUE WHERE id = :cid"),
            {"cid": call_id},
        )
        await db.commit()

    logger.info(f"[{call_id}] Action confirmed: {action_type} — {action_summary}")
    return {
        "confirmed": True,
        "action_type": action_type,
        "summary": action_summary,
        "message": f"Done. {action_summary}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ── escalate_to_human ───────────────────────────────────────────────────────

async def escalate_to_human(
    reason: str,
    call_id: str,
    transcript_summary: str = "",
    steps_completed: list | None = None,
    **_extra,
) -> dict:
    session = get_session(call_id)
    if session:
        session.escalated = True
        session.escalation_reason = reason

    async with AsyncSessionLocal() as db:
        await db.execute(
            text("""
                UPDATE calls
                SET escalated = TRUE, escalation_reason = :r, escalation_at = NOW()
                WHERE id = :cid
            """),
            {"r": reason, "cid": call_id},
        )
        await db.commit()

    handoff = {
        "call_id": call_id,
        "reason": reason,
        "transcript_summary": transcript_summary,
        "steps_completed": steps_completed or [],
        "auth_state": session.auth_state.state.value if session else "unknown",
        "customer_id": session.customer_id if session else None,
        "conversation_history": session.conversation_history[-20:] if session else [],
    }

    logger.info(f"[{call_id}] Escalating: {reason}")
    return {
        "escalated": True,
        "reason": reason,
        "handoff_bundle": handoff,
        "message": "Connecting you to a human agent now. Please hold.",
    }


# ── get_order_status ─────────────────────────────────────────────────────────

async def get_order_status(customer_id: str, order_id: str | None = None) -> dict:
    async with AsyncSessionLocal() as db:
        if order_id:
            result = await db.execute(
                text("""
                    SELECT txn_number, merchant, amount, currency,
                           txn_type, status, txn_date, gateway_ref
                    FROM transactions
                    WHERE customer_id = :cid AND txn_number = :txn
                """),
                {"cid": customer_id, "txn": order_id.upper()},
            )
            row = result.mappings().first()
            if not row:
                return {"found": False, "error": f"Transaction {order_id} not found"}
            return {"found": True, "order": dict(row)}

        result = await db.execute(
            text("""
                SELECT txn_number, merchant, amount, currency,
                       txn_type, status, txn_date, gateway_ref
                FROM transactions
                WHERE customer_id = :cid
                ORDER BY txn_date DESC
            """),
            {"cid": customer_id},
        )
        orders = [dict(r) for r in result.mappings().all()]

    return {"found": True, "orders": orders, "count": len(orders)}


# ── get_call_history ──────────────────────────────────────────────────────────

async def get_call_history(customer_id: str, limit: int = 3) -> dict:
    limit = min(limit, 10)
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            text("""
                SELECT c.id, c.started_at, c.ended_at, c.resolution,
                       c.escalation_reason, c.acw_summary,
                       e.overall_score
                FROM calls c
                LEFT JOIN eval_scores e ON e.call_id = c.id
                WHERE c.customer_id = :cid AND c.status = 'completed'
                ORDER BY c.started_at DESC
                LIMIT :lim
            """),
            {"cid": customer_id, "lim": limit},
        )
        rows = result.mappings().all()

    calls = []
    for r in rows:
        calls.append({
            "call_id": str(r["id"]),
            "date": r["started_at"].isoformat() if r["started_at"] else None,
            "resolution": r["resolution"],
            "escalation_reason": r["escalation_reason"],
            "summary": r["acw_summary"],
            "qa_score": r["overall_score"],
        })

    return {"calls": calls, "count": len(calls)}


# ── Master dispatcher ─────────────────────────────────────────────────────────

async def execute_tool(tool_name: str, tool_args: dict, call_id: str) -> dict:
    """Called after the guardrail pipeline has approved the tool call."""
    match tool_name:
        case "lookup_account":
            return await lookup_account(call_id=call_id, **tool_args)
        case "send_2fa":
            return await send_2fa(call_id=call_id, **tool_args)
        case "verify_2fa":
            return await verify_2fa(call_id=call_id, **tool_args)
        case "update_record":
            return await update_record(call_id=call_id, **tool_args)
        case "confirm_action":
            return await confirm_action(call_id=call_id, **tool_args)
        case "escalate_to_human":
            return await escalate_to_human(call_id=call_id, **tool_args)
        case "get_order_status":
            return await get_order_status(**tool_args)
        case "get_call_history":
            return await get_call_history(**tool_args)
        case "crm_search":
            from tools.crm_query import crm_search
            return await crm_search(**tool_args)
        case _:
            return {"error": f"Unknown tool: {tool_name}"}
