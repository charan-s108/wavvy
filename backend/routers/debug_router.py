"""
Dev-only debug inspector.

ONLY active when ENVIRONMENT=development. Returns zero data in production.

Endpoints:
  GET /api/debug/session/{call_id}   — live CallSession state (no DB hit)
  GET /api/debug/customer/{phone}    — full DB row for a customer (unmasked)
  GET /api/debug/calls/recent        — last 10 call rows from DB
  GET /api/debug/sessions            — all currently active CallSession IDs
"""
import re
import uuid as _uuid
from datetime import timezone

from fastapi import APIRouter
from sqlalchemy import text

from config import settings
from database import AsyncSessionLocal
from session.call_session import ACTIVE_CALLS

router = APIRouter(prefix="/api/debug", tags=["debug"])

_DEV = settings.environment == "development"


def _guard():
    if not _DEV:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Not found")


# ── /api/debug/session/{call_id} ─────────────────────────────────────────────

@router.get("/session/{call_id}")
async def inspect_session(call_id: str):
    """Dump the live CallSession for a running call — no DB needed."""
    _guard()
    session = ACTIVE_CALLS.get(call_id)
    if not session:
        return {
            "found": False,
            "active_call_ids": list(ACTIVE_CALLS.keys()),
        }

    started = getattr(session, "started_at", None)
    duration = None
    if started:
        from datetime import datetime
        duration = int((datetime.now(timezone.utc) - started).total_seconds())

    return {
        "found": True,
        "call_id": call_id,
        "duration_sec": duration,

        # Identity
        "customer_id":    session.customer_id,
        "confirmed_name": session.confirmed_name,
        "confirmed_email": session.confirmed_email,

        # Full cached profile (set by verify_account)
        "customer_profile": session.customer_profile,

        # OTP state
        "otp_code":     session.otp_code,
        "otp_verified": session.otp_verified,

        # Escalation
        "escalated":      session.escalated,
        "human_joined":   session.human_joined,
        "handoff_bundle": session.handoff_bundle,

        # Conversation
        "turn_count":          session.turn_count,
        "conversation_turns":  len(session.conversation_history),
        "last_transcript":     session._last_transcript,
        "pending_escalation":  session.pending_escalation,
        "pending_slot":        session.pending_slot,

        # Tool tracking
        "last_tool_attempted": session._last_tool_attempted,
        "tool_last_called":    {
            k: v.isoformat() if hasattr(v, "isoformat") else str(v)
            for k, v in session._tool_last_called.items()
        },
    }


# ── /api/debug/sessions ───────────────────────────────────────────────────────

@router.get("/sessions")
async def list_sessions():
    """Show all currently active call session IDs."""
    _guard()
    return {
        "active_count": len(ACTIVE_CALLS),
        "call_ids": list(ACTIVE_CALLS.keys()),
    }


# ── /api/debug/customer/{phone} ───────────────────────────────────────────────

@router.get("/customer/{phone}")
async def inspect_customer(phone: str):
    """Return the full DB row for a customer (unmasked). Dev only."""
    _guard()
    digits = re.sub(r"[^\d]", "", phone)

    async with AsyncSessionLocal() as db:
        # Exact match
        result = await db.execute(
            text("""
                SELECT id, name, phone, email, account_type,
                       account_status, fraud_hold_active, kyc_status,
                       created_at, updated_at
                FROM customers
                WHERE regexp_replace(phone, '[^0-9]', '', 'g') = :v
            """),
            {"v": digits},
        )
        row = result.mappings().first()

        # Suffix match fallback
        if not row and len(digits) >= 7:
            result = await db.execute(
                text("""
                    SELECT id, name, phone, email, account_type,
                           account_status, fraud_hold_active, kyc_status,
                           created_at, updated_at
                    FROM customers
                    WHERE regexp_replace(phone, '[^0-9]', '', 'g') LIKE :suffix
                """),
                {"suffix": f"%{digits}"},
            )
            row = result.mappings().first()

        if not row:
            return {"found": False, "searched_digits": digits}

        cid = row["id"]
        txn_result = await db.execute(
            text("""
                SELECT txn_number, merchant, amount, txn_type, status, txn_date
                FROM transactions WHERE customer_id = :cid ORDER BY txn_date DESC
            """),
            {"cid": cid},
        )
        transactions = [dict(r) for r in txn_result.mappings().all()]

    return {
        "found": True,
        "id":              str(row["id"]),
        "name":            row["name"],
        "phone":           row["phone"],
        "email":           row["email"],
        "account_type":    row["account_type"],
        "account_status":  row["account_status"],
        "fraud_hold_active": row["fraud_hold_active"],
        "kyc_status":      row["kyc_status"],
        "transactions":    transactions,
        "created_at":      row["created_at"].isoformat() if row["created_at"] else None,
        "updated_at":      row["updated_at"].isoformat() if row["updated_at"] else None,
    }


# ── /api/debug/calls/recent ───────────────────────────────────────────────────

@router.get("/calls/recent")
async def recent_calls(limit: int = 10):
    """Last N call rows from the DB — quick post-call verification."""
    _guard()
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            text("""
                SELECT c.id, c.started_at, c.ended_at, c.duration_secs,
                       c.escalated, c.escalation_reason, c.status, c.resolution,
                       cu.name AS customer_name, cu.phone AS customer_phone
                FROM calls c
                LEFT JOIN customers cu ON c.customer_id = cu.id
                ORDER BY c.started_at DESC
                LIMIT :lim
            """),
            {"lim": limit},
        )
        rows = result.mappings().all()

    return {
        "count": len(rows),
        "calls": [
            {
                "call_id":        str(r["id"]),
                "customer_name":  r["customer_name"],
                "customer_phone": r["customer_phone"],
                "started_at":     r["started_at"].isoformat() if r["started_at"] else None,
                "ended_at":       r["ended_at"].isoformat() if r["ended_at"] else None,
                "duration_secs":  r["duration_secs"],
                "status":         r["status"],
                "resolution":     r["resolution"],
                "escalated":      r["escalated"],
                "escalation_reason": r["escalation_reason"],
            }
            for r in rows
        ],
    }
