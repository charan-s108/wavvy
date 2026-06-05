"""
Wavvy self-demo tool implementations.
Tools: capture_lead, schedule_demo, cancel_demo, escalate_to_human.
All async. Called only via execute_with_recovery() — never directly.

schedule_demo responsibilities:
  - Delegates slot resolution to scheduling_agent.resolve_slot()
  - Returns needs_clarification=True when confidence is too low
  - Returns needs_confirmation=True when an alternative slot is suggested
  - Books directly when slot is confirmed (force_slot) or free

cancel_demo responsibilities:
  - Delegates to scheduling_agent.cancel_appointment()
  - Returns success/failure with slot label for UI feedback
"""
import asyncio
import json
import logging
import uuid as _uuid
from datetime import datetime, timezone, timedelta

import httpx
from sqlalchemy import text

import database as _db_module
from config import settings
from constants.transaction_status import (
    FAILED, COMPLETED, FLAGGED, PENDING, PROCESSING, CANCELLED, EXPIRED,
    REFUND_INITIATED, REFUND_PROCESSING, REFUND_COMPLETED,
    KYC_HOLD, COMPLIANCE_HOLD,
    DISPUTED, CHARGEBACK_INITIATED, CHARGEBACK_WON, CHARGEBACK_LOST,
    FRAUD_REPORTED, FRAUD_CONFIRMED, FRAUD_REVERSED,
)
from session.call_session import get_session, ACTIVE_CALLS

logger = logging.getLogger(__name__)


# ── capture_lead ─────────────────────────────────────────────────────────────

async def capture_lead(
    name: str,
    email: str | None,
    phone: str | None,
    company: str | None,
    intent: str,
    call_id: str,
) -> dict:
    """
    Saves lead info to the leads table.
    Returns {success, lead_id, fast_response_key}.
    Idempotent: if call_id already has a lead row, upserts it.
    """
    async with _db_module.AsyncSessionLocal() as db:
        # Check for existing lead on this call
        existing = await db.execute(
            text("SELECT id FROM leads WHERE call_id = :call_id"),
            {"call_id": call_id},
        )
        row = existing.mappings().first()

        if row:
            # Update existing lead
            await db.execute(
                text("""
                    UPDATE leads
                    SET name = COALESCE(:name, name),
                        email = COALESCE(:email, email),
                        phone = COALESCE(:phone, phone),
                        company = COALESCE(:company, company),
                        intent = :intent
                    WHERE call_id = :call_id
                """),
                {
                    "name": name, "email": email, "phone": phone,
                    "company": company, "intent": intent, "call_id": call_id,
                },
            )
            lead_id = str(row["id"])
        else:
            # Insert new lead
            result = await db.execute(
                text("""
                    INSERT INTO leads (call_id, name, email, phone, company, intent)
                    VALUES (:call_id, :name, :email, :phone, :company, :intent)
                    RETURNING id
                """),
                {
                    "call_id": call_id, "name": name, "email": email,
                    "phone": phone, "company": company, "intent": intent,
                },
            )
            lead_id = str(result.scalar())

        await db.commit()

    # Update session lead_id
    session = get_session(call_id)
    if session:
        session.lead_id = lead_id

    logger.info(json.dumps({
        "call_id": call_id, "tool": "capture_lead",
        "lead_id": lead_id, "name": name, "intent": intent,
    }))

    return {
        "success": True,
        "lead_id": lead_id,
        "fast_response_key": "lead_captured",
        "template_vars": {"name": name},
    }


# ── schedule_demo ─────────────────────────────────────────────────────────────

async def schedule_demo(
    lead_id: str | None,
    name: str,
    email: str | None,
    preferred_time: str,
    call_id: str,
    force_slot: dict | None = None,   # pre-confirmed slot from pending confirmation
    user_timezone: str = "Asia/Kolkata",
    **_extra,
) -> dict:
    """
    Resolve a preferred time and book a demo appointment.

    Possible outcomes:
      needs_clarification=True  → parse confidence too low; return clarification prompt
      needs_confirmation=True   → alternative slot found; wait for user confirm
      success=True              → booked; return confirmation details
    """
    from agents.scheduling_agent import (
        resolve_slot, send_confirmation_email, _slot_key,
    )
    from datetime import datetime as _dt

    if force_slot:
        # User already confirmed a suggested alternative — book directly
        confirmed_time = _dt.fromisoformat(force_slot["confirmed_time_iso"])
        lbl       = force_slot["slot_label"]
        lbl_short = force_slot["slot_label_short"]
    else:
        slot_info = await resolve_slot(preferred_time, user_timezone)

        # Low confidence → ask for clarification; do NOT book
        if slot_info.get("needs_clarification"):
            return {
                "success":             True,
                "needs_clarification": True,
                "clarification_key":   slot_info["clarification_key"],
                "clarification_vars":  slot_info["clarification_vars"],
                "parse_confidence":    slot_info.get("parse_confidence", 0.0),
            }

        if slot_info.get("alt_reason") == "no_slots":
            return {
                "success": False,
                "fast_response_key": "no_slots_available",
            }

        confirmed_time = slot_info["confirmed_time"]
        lbl            = slot_info["slot_label"]
        lbl_short      = slot_info["slot_label_short"]
        is_alt         = slot_info.get("is_alternative", False)
        alt_reason     = slot_info.get("alt_reason")

        if is_alt:
            # Suggest alternative; do NOT book until user confirms
            suggest_key = (
                "demo_slot_suggest_out_of_hours"
                if alt_reason == "out_of_hours"
                else "demo_slot_suggest_conflict"
            )
            return {
                "success":           True,
                "needs_confirmation": True,
                "pending_slot": {
                    "confirmed_time_iso": confirmed_time.isoformat(),
                    "slot_label":         lbl,
                    "slot_label_short":   lbl_short,
                    "alt_reason":         alt_reason,
                },
                "fast_response_key": suggest_key,
                "template_vars":     {"slot_label": lbl_short},
            }

    # ── Book the appointment ──────────────────────────────────────────────────
    sk = _slot_key(confirmed_time)

    async with _db_module.AsyncSessionLocal() as db:
        if not lead_id:
            result = await db.execute(
                text("""
                    INSERT INTO leads (call_id, name, email, intent, status)
                    VALUES (:call_id, :name, :email, 'demo_request', 'demo_scheduled')
                    RETURNING id
                """),
                {"call_id": call_id, "name": name, "email": email},
            )
            lead_id = str(result.scalar())
        else:
            await db.execute(
                text("UPDATE leads SET status = 'demo_scheduled' WHERE id = :id"),
                {"id": lead_id},
            )

        try:
            result = await db.execute(
                text("""
                    INSERT INTO demo_appointments
                        (lead_id, call_id, requested_time, confirmed_time,
                         slot_label, slot_key, user_timezone, status)
                    VALUES
                        (:lead_id, :call_id, :req, :confirmed,
                         :lbl, :slot_key, :tz, 'confirmed')
                    RETURNING id
                """),
                {
                    "lead_id":   lead_id, "call_id": call_id,
                    "req":       preferred_time, "confirmed": confirmed_time,
                    "lbl":       lbl, "slot_key": sk, "tz": user_timezone,
                },
            )
            appointment_id = str(result.scalar())
            await db.commit()
        except Exception as exc:
            # Unique constraint violation (concurrent booking race) — surface cleanly
            if "uniq_confirmed_slot" in str(exc) or "unique" in str(exc).lower():
                logger.warning(json.dumps({
                    "call_id": call_id, "tool": "schedule_demo",
                    "event": "slot_race_condition", "slot_key": sk,
                }))
                return {
                    "success": False,
                    "fast_response_key": "slot_just_taken",
                }
            raise

    if email:
        asyncio.create_task(send_confirmation_email(name, email, lbl, call_id))

    logger.info(json.dumps({
        "call_id": call_id, "tool": "schedule_demo",
        "lead_id": lead_id, "appointment_id": appointment_id,
        "requested_time": preferred_time, "confirmed_time": str(confirmed_time),
        "slot_key": sk, "force_slot": bool(force_slot),
    }))

    return {
        "success":           True,
        "appointment_id":    appointment_id,
        "fast_response_key": "demo_scheduled",
        "template_vars": {
            "name":       name,
            "email":      email or "your email",
            "slot_label": lbl_short,
        },
    }


# ── cancel_demo ───────────────────────────────────────────────────────────────

async def cancel_demo(call_id: str, **_extra) -> dict:
    """
    Cancel the caller's most recent confirmed demo appointment.
    Delegates to scheduling_agent.cancel_appointment for DB + email.
    """
    from agents.scheduling_agent import cancel_appointment
    result = await cancel_appointment(call_id)

    if not result.get("success"):
        reason = result.get("reason", "unknown")
        fast_key = "no_appointment_found" if reason == "no_active_appointment" else "tool_error"
        return {"success": False, "fast_response_key": fast_key}

    logger.info(json.dumps({
        "call_id": call_id, "tool": "cancel_demo",
        "appointment_id": result.get("appointment_id"),
        "slot_label": result.get("slot_label"),
    }))

    return {
        "success":           True,
        "appointment_id":    result.get("appointment_id"),
        "fast_response_key": "demo_cancelled",
        "template_vars": {
            "name":       result.get("name") or "",
            "slot_label": result.get("slot_label") or "your demo",
        },
    }


# ── escalate_to_human ─────────────────────────────────────────────────────────

async def escalate_to_human(
    reason: str,
    lead_summary: str,
    call_id: str,
) -> dict:
    """
    Marks the call as escalated and notifies the agent desktop via WebSocket.
    Builds an EscalationPacket from session state and sends it.
    """
    from models.escalation_packet import build_escalation_packet
    from voice.events import emit, EscalationRequestedEvent

    session = get_session(call_id)
    if not session:
        logger.error(f"[{call_id}] escalate_to_human: no active session")
        return {"success": False, "fast_response_key": "tool_error"}

    if session.escalated:
        return {"success": True, "fast_response_key": "already_escalated"}

    # Server-side identity gate: customer must be verified before escalation.
    # This prevents the LLM from skipping identity collection.
    if not session.customer_id:
        logger.info(f"[{call_id}] escalate_to_human blocked — customer not verified")
        return {
            "success": False,
            "fast_response_key": "verify_before_escalate",
            "say_this": "I'd love to connect you with a specialist, but I need to verify your identity first for security. Could you share your phone number so I can look up your account? Once I've confirmed who you are, I'll transfer you straight away.",
            "next_step": "Call verify_account with the phone number they provide. After verify_account succeeds, call escalate_to_human again immediately.",
        }

    packet = build_escalation_packet(session, reason=reason)
    packet_dict = packet.to_dict() if packet else {}

    if packet:
        await emit(EscalationRequestedEvent(
            call_id=call_id,
            reason=reason,
            packet=packet,
        ))

    session.escalated = True
    session.conv_state.mark_escalated()

    # Text-to-TTS model: no separate room needed. Agent types → agent-say endpoint
    # sends LiveKit data message → worker calls agent_session.say(text).
    esc_room_name: str | None = None
    customer_esc_token: str | None = None
    agent_esc_token: str | None = None

    # Update call record — asyncpg requires UUID objects for UUID columns
    async with _db_module.AsyncSessionLocal() as db:
        await db.execute(
            text("""
                UPDATE calls
                SET escalated = TRUE,
                    escalation_reason = :reason,
                    escalation_at = NOW()
                WHERE id = :call_id
            """),
            {"reason": reason, "call_id": _uuid.UUID(call_id)},
        )
        await db.commit()

    logger.info(json.dumps({
        "call_id": call_id, "tool": "escalate_to_human", "reason": reason,
    }))

    return {
        "success": True,
        "fast_response_key": "escalating",
        "handoff_bundle": packet_dict,
        "esc_room_name": esc_room_name,
        "customer_esc_token": customer_esc_token,
        "agent_esc_token": agent_esc_token,
        "livekit_url": settings.livekit_url,
    }


# ── verify_account ────────────────────────────────────────────────────────────

import re as _re

def _normalize_phone_digits(raw: str) -> str:
    return _re.sub(r"[^\d]", "", raw)


async def verify_account(phone: str, call_id: str) -> dict:
    """
    Look up a customer by phone number and cache the customer_id on the session.
    Returns masked identity fields only — raw PII never reaches the LLM.
    """
    digits = _normalize_phone_digits(phone)

    row = None
    async with _db_module.AsyncSessionLocal() as db:
        result = await db.execute(
            text("""
                SELECT id, name, phone, email, account_type,
                       account_status, fraud_hold_active, kyc_status
                FROM customers
                WHERE regexp_replace(phone, '[^0-9]', '', 'g') = :v
            """),
            {"v": digits},
        )
        row = result.mappings().first()

        if not row and len(digits) >= 7:
            for suffix_len in (len(digits), len(digits) - 1, 10):
                if suffix_len < 7:
                    break
                suffix = digits[-suffix_len:] if suffix_len < len(digits) else digits
                result = await db.execute(
                    text("""
                        SELECT id, name, phone, email, account_type,
                               account_status, fraud_hold_active, kyc_status
                        FROM customers
                        WHERE regexp_replace(phone, '[^0-9]', '', 'g') LIKE :suffix
                    """),
                    {"suffix": f"%{suffix}"},
                )
                row = result.mappings().first()
                if row:
                    break

        if not row:
            session = get_session(call_id)
            if session:
                session.verify_account_attempts += 1
            attempts = session.verify_account_attempts if session else 1
            logger.info(json.dumps({"call_id": call_id, "tool": "verify_account", "found": False, "attempts": attempts}))
            return {
                "success": False,
                "found": False,
                "attempts": attempts,
                "fast_response_key": "account_not_found",
            }

        cid = row["id"]

        # Load transactions
        txn_result = await db.execute(
            text("""
                SELECT txn_number, merchant, amount, currency, txn_type,
                       status, txn_date, gateway_ref
                FROM transactions
                WHERE customer_id = :cid
                ORDER BY txn_date DESC
            """),
            {"cid": cid},
        )
        transactions = [
            {
                "txn_number":  r["txn_number"],
                "merchant":    r["merchant"],
                "amount":      float(r["amount"]),
                "currency":    r["currency"],
                "txn_type":    r["txn_type"],
                "status":      r["status"],
                "txn_date":    str(r["txn_date"]),
                "gateway_ref": r["gateway_ref"],
            }
            for r in txn_result.mappings().all()
        ]

        # Load active account holds
        holds_result = await db.execute(
            text("""
                SELECT hold_type, status, reason, placed_at
                FROM account_holds
                WHERE customer_id = :cid AND status = 'active'
                ORDER BY placed_at DESC
            """),
            {"cid": cid},
        )
        account_holds_data = [
            {
                "hold_type": r["hold_type"],
                "reason":    r["reason"],
                "placed_at": str(r["placed_at"]) if r["placed_at"] else None,
            }
            for r in holds_result.mappings().all()
        ]

        # Load non-terminal refunds (initiated / processing)
        refunds_result = await db.execute(
            text("""
                SELECT r.rfn_number, r.amount AS refund_amount, r.status,
                       r.initiated_at, t.txn_number AS transaction_id, t.merchant
                FROM refunds r
                JOIN transactions t ON r.transaction_id = t.id
                WHERE r.customer_id = :cid
                  AND r.status NOT IN ('completed', 'rejected')
                ORDER BY r.initiated_at DESC
            """),
            {"cid": cid},
        )
        open_refunds = [
            {
                "rfn_number":     r["rfn_number"],
                "transaction_id": r["transaction_id"],
                "merchant":       r["merchant"],
                "amount":         float(r["refund_amount"]),
                "status":         r["status"],
                "initiated_at":   str(r["initiated_at"]) if r["initiated_at"] else None,
            }
            for r in refunds_result.mappings().all()
        ]

        # Load non-terminal disputes (open / under_review)
        disputes_result = await db.execute(
            text("""
                SELECT d.dsp_number, d.reason, d.status, d.opened_at,
                       t.txn_number AS transaction_id, t.merchant,
                       t.amount AS txn_amount
                FROM disputes d
                JOIN transactions t ON d.transaction_id = t.id
                WHERE d.customer_id = :cid
                  AND d.status NOT IN ('resolved_won', 'resolved_lost', 'closed')
                ORDER BY d.opened_at DESC
            """),
            {"cid": cid},
        )
        open_disputes = [
            {
                "dsp_number":     r["dsp_number"],
                "transaction_id": r["transaction_id"],
                "merchant":       r["merchant"],
                "amount":         float(r["txn_amount"]),
                "reason":         r["reason"],
                "status":         r["status"],
                "opened_at":      str(r["opened_at"]) if r["opened_at"] else None,
            }
            for r in disputes_result.mappings().all()
        ]

        # Load active fraud cases under review
        fraud_result = await db.execute(
            text("""
                SELECT fc.fraud_number, fc.fraud_type, fc.status, fc.risk_level,
                       fc.hold_placed_at, t.txn_number AS transaction_id
                FROM fraud_cases fc
                LEFT JOIN transactions t ON fc.transaction_id = t.id
                WHERE fc.customer_id = :cid AND fc.status = 'under_review'
                ORDER BY fc.hold_placed_at DESC
            """),
            {"cid": cid},
        )
        active_fraud_cases = [
            {
                "fraud_number":   r["fraud_number"],
                "transaction_id": r["transaction_id"],
                "fraud_type":     r["fraud_type"],
                "risk_level":     r["risk_level"],
                "status":         r["status"],
                "hold_placed_at": str(r["hold_placed_at"]) if r["hold_placed_at"] else None,
            }
            for r in fraud_result.mappings().all()
        ]

    customer_id = str(row["id"])
    name = row["name"] or ""
    phone_raw = row["phone"] or ""
    email_raw = row["email"] or ""

    masked_phone = f"***{phone_raw[-3:]}" if len(phone_raw) >= 3 else "***"
    at = email_raw.find("@")
    masked_email = (
        f"{email_raw[:2]}***{email_raw[at:]}" if at > 2 else "***"
    )
    first_name = name.split()[0] if name else "customer"

    session = get_session(call_id)
    if session:
        session.customer_id = customer_id
        session.verify_account_attempts = 0
        session.customer_profile = {
            "name":               name,
            "first_name":         first_name,
            "email":              email_raw,
            "phone":              phone_raw,
            "account_type":       row["account_type"] or "standard",
            "account_status":     row["account_status"] or "active",
            "fraud_hold_active":  bool(row["fraud_hold_active"]),
            "kyc_status":         row["kyc_status"] or "pending",
            "masked_phone":       masked_phone,
            "masked_email":       masked_email,
            "transactions":       transactions,
            "account_holds":      account_holds_data,
            "open_refunds":       open_refunds,
            "open_disputes":      open_disputes,
            "active_fraud_cases": active_fraud_cases,
        }

    logger.info(json.dumps({
        "call_id": call_id, "tool": "verify_account",
        "customer_id": customer_id, "found": True,
    }))

    fraud_note = (
        f"Active fraud cases ({len(active_fraud_cases)}): " +
        ", ".join(
            f"{fc['fraud_number']} ({fc['fraud_type']}, {fc['status']})"
            for fc in active_fraud_cases
        )
        if active_fraud_cases
        else "NO fraud cases on record for this customer. Do NOT mention, imply, or invent any fraud case or fraud reference number."
    )

    return {
        "success": True,
        "found": True,
        "customer_id": customer_id,
        "first_name": first_name,
        "account_type": row["account_type"] or "standard",
        "masked_phone": masked_phone,
        "masked_email": masked_email,
        "fraud_cases": fraud_note,
        "fast_response_key": "account_verified",
        "template_vars": {"name": first_name},
    }


# ── lookup_transaction ────────────────────────────────────────────────────────

async def lookup_transaction(transaction_id: str, call_id: str) -> dict:
    """
    Look up a transaction by txn_number for the verified customer.
    Uses session cache populated by verify_account; falls back to DB.
    """
    session = get_session(call_id)
    customer_id = getattr(session, "customer_id", None) if session else None

    if not customer_id:
        return {"success": False, "fast_response_key": "verification_required"}

    txn_id_upper = transaction_id.upper()
    cached_profile = getattr(session, "customer_profile", None) if session else None

    if cached_profile is not None:
        transactions = cached_profile.get("transactions") or []
        match = next(
            (t for t in transactions if str(t.get("txn_number", "")).upper() == txn_id_upper),
            None,
        )
    else:
        async with _db_module.AsyncSessionLocal() as db:
            result = await db.execute(
                text("""
                    SELECT txn_number, merchant, amount, currency, txn_type,
                           status, txn_date, gateway_ref
                    FROM transactions
                    WHERE customer_id = :cid AND UPPER(txn_number) = :txn
                """),
                {"cid": _uuid.UUID(customer_id), "txn": txn_id_upper},
            )
            row = result.mappings().first()
        if not row:
            return {"success": True, "found": False, "fast_response_key": "transaction_not_found"}
        match = dict(row)

    if not match:
        logger.info(json.dumps({
            "call_id": call_id, "tool": "lookup_transaction",
            "transaction_id": transaction_id, "found": False,
        }))
        return {"success": True, "found": False, "fast_response_key": "transaction_not_found"}

    logger.info(json.dumps({
        "call_id": call_id, "tool": "lookup_transaction",
        "transaction_id": transaction_id, "found": True,
        "status": match.get("status"),
    }))

    txn_num = match.get("txn_number", transaction_id)
    return {
        "success": True,
        "found": True,
        "transaction_id": txn_num,
        "merchant": match.get("merchant"),
        "amount": match.get("amount"),
        "type": match.get("txn_type"),
        "status": match.get("status"),
        "date": match.get("txn_date"),
        "fast_response_key": "transaction_found",
        "template_vars": {
            "transaction_id": txn_num,
            "merchant": match.get("merchant"),
            "amount": match.get("amount"),
            "status": match.get("status"),
        },
    }


# ── send_otp ─────────────────────────────────────────────────────────────────

import random as _random

async def send_otp(call_id: str) -> dict:
    """Generate a 6-digit demo OTP and store it on the session.
    Enforces: 30s resend cooldown, 5 sends/session max.
    """
    session = get_session(call_id)
    if not session:
        return {"success": False}

    # Cooldown: 10s minimum between sends (voice calls are real-time)
    if session.otp_sent_at:
        elapsed = (datetime.now(timezone.utc) - session.otp_sent_at).total_seconds()
        if elapsed < 10:
            return {
                "success": False,
                "fast_response_key": "otp_cooldown",
                "retry_in_seconds": int(10 - elapsed),
            }

    # Cap total sends this session
    if session.otp_resend_count >= 5:
        return {"success": False, "fast_response_key": "otp_resend_limit"}

    otp = str(_random.randint(100000, 999999))
    session.otp_code = otp
    session.otp_verified = False
    session.otp_sent_at = datetime.now(timezone.utc)
    session.otp_attempts = 0       # reset wrong-code counter on each new send
    session.otp_locked = False
    session.otp_resend_count += 1

    logger.info(json.dumps({"call_id": call_id, "tool": "send_otp",
                             "resend_count": session.otp_resend_count}))
    return {"success": True, "otp": otp, "fast_response_key": "otp_sent"}


# ── verify_otp ────────────────────────────────────────────────────────────────

async def verify_otp(otp_input: str, call_id: str) -> dict:
    """Validate the OTP entered by the customer.
    Enforces: 5-min expiry, 3-attempt lock, locked-state guard.
    """
    session = get_session(call_id)
    if not session or not session.otp_code:
        return {"success": False, "fast_response_key": "no_otp_pending"}

    # Expiry check (5 minutes)
    if session.otp_sent_at:
        elapsed = (datetime.now(timezone.utc) - session.otp_sent_at).total_seconds()
        if elapsed > 300:
            session.otp_code = None
            logger.info(json.dumps({"call_id": call_id, "tool": "verify_otp", "result": "expired"}))
            return {"success": False, "fast_response_key": "otp_expired"}

    # Already locked after 3 failures
    if session.otp_locked:
        return {"success": False, "fast_response_key": "otp_max_attempts"}

    clean = otp_input.strip().replace(" ", "").replace("-", "")
    session.otp_attempts += 1

    if clean == session.otp_code:
        session.otp_verified = True
        logger.info(json.dumps({"call_id": call_id, "tool": "verify_otp", "result": "success"}))
        return {"success": True, "fast_response_key": "otp_verified"}

    # Wrong code
    if session.otp_attempts >= 3:
        session.otp_locked = True
        logger.info(json.dumps({"call_id": call_id, "tool": "verify_otp",
                                 "result": "locked", "attempts": session.otp_attempts}))
        return {"success": False, "fast_response_key": "otp_max_attempts"}

    remaining = 3 - session.otp_attempts
    logger.info(json.dumps({"call_id": call_id, "tool": "verify_otp",
                             "result": "wrong", "attempts": session.otp_attempts,
                             "remaining": remaining}))
    return {"success": False, "fast_response_key": "otp_wrong",
            "attempts_remaining": remaining}


# ── unlock_account ────────────────────────────────────────────────────────────

async def unlock_account(call_id: str) -> dict:
    """Unlock the verified customer's account. Requires otp_verified on session."""
    session = get_session(call_id)
    if not session or not session.otp_verified:
        return {"success": False, "fast_response_key": "verification_required"}
    if not session.customer_id:
        return {"success": False, "fast_response_key": "verification_required"}

    async with _db_module.AsyncSessionLocal() as db:
        result = await db.execute(
            text("""
                SELECT account_status, fraud_hold_active, kyc_status
                FROM customers WHERE id = :id
            """),
            {"id": _uuid.UUID(session.customer_id)},
        )
        row = result.mappings().first()

    if not row:
        return {"success": False, "fast_response_key": "account_not_found"}

    if row["fraud_hold_active"]:
        return {"success": False, "fast_response_key": "fraud_lock"}
    if row["account_status"] == "frozen":
        return {"success": False, "fast_response_key": "compliance_hold"}

    async with _db_module.AsyncSessionLocal() as db:
        await db.execute(
            text("""
                UPDATE customers
                SET account_status = 'active',
                    account_locked_at = NULL,
                    account_locked_reason = NULL
                WHERE id = :id
            """),
            {"id": _uuid.UUID(session.customer_id)},
        )
        await db.commit()

    logger.info(json.dumps({"call_id": call_id, "tool": "unlock_account", "customer_id": session.customer_id}))
    return {"success": True, "fast_response_key": "account_unlocked"}


# ── initiate_refund ───────────────────────────────────────────────────────────

async def initiate_refund(transaction_id: str, call_id: str) -> dict:
    """Initiate a refund for a failed transaction.
    Pre-checks transaction status before writing. Idempotent within session.
    Requires OTP verification (otp_verified=True) before executing.
    """
    session = get_session(call_id)
    if not session or not session.otp_verified:
        logger.warning(json.dumps({
            "call_id": call_id,
            "tool": "initiate_refund",
            "event": "blocked_otp_not_verified",
            "otp_verified": getattr(session, "otp_verified", None),
        }))
        return {"success": False, "fast_response_key": "verification_required"}
    if not session.customer_id:
        return {"success": False, "fast_response_key": "verification_required"}

    txn_upper = transaction_id.upper()

    # Idempotency: if a refund case was already opened this session, don't re-initiate
    if session.refund_case_id:
        return {
            "success": False,
            "fast_response_key": "refund_already_initiated",
            "refund_case_id": session.refund_case_id,
            "estimated_days": "3–5 business days",
        }

    from utils.ref_numbers import next_rfn_number

    async with _db_module.AsyncSessionLocal() as db:
        result = await db.execute(
            text("""
                SELECT id, txn_number, status, amount
                FROM transactions
                WHERE customer_id = :cid AND UPPER(txn_number) = :txn
            """),
            {"cid": _uuid.UUID(session.customer_id), "txn": txn_upper},
        )
        txn_row = result.mappings().first()

    if not txn_row:
        return {"success": False, "fast_response_key": "transaction_not_found"}

    status = txn_row["status"] or ""

    if status in (REFUND_INITIATED, REFUND_PROCESSING):
        return {
            "success": False,
            "fast_response_key": "refund_already_initiated",
            "estimated_days": "3–5 business days",
        }
    if status == REFUND_COMPLETED:
        return {"success": False, "fast_response_key": "refund_already_completed"}
    if status == COMPLETED:
        return {
            "success": False,
            "fast_response_key": "refund_ineligible",
            "reason": "Transaction completed successfully. Route to disputes team.",
        }
    if status == FLAGGED:
        return {
            "success": False,
            "fast_response_key": "fraud_review_required",
            "reason": "Transaction under fraud review. Escalate immediately.",
        }
    if status == KYC_HOLD:
        return {
            "success": False,
            "fast_response_key": "kyc_escalation_required",
            "reason": "Account KYC hold active. Cannot process refund.",
        }

    async with _db_module.AsyncSessionLocal() as db:
        rfn_number = await next_rfn_number(db)

        await db.execute(
            text("UPDATE transactions SET status = :status WHERE id = :id"),
            {"status": REFUND_INITIATED, "id": txn_row["id"]},
        )
        await db.execute(
            text("""
                INSERT INTO refunds (rfn_number, transaction_id, customer_id,
                                     amount, status, initiated_by, call_id)
                VALUES (:rfn, :tid, :cid, :amount, 'initiated', :by, :call_id)
            """),
            {
                "rfn": rfn_number,
                "tid": txn_row["id"],
                "cid": _uuid.UUID(session.customer_id),
                "amount": float(txn_row["amount"]),
                "by": f"voice_ai_{call_id}",
                "call_id": call_id,
            },
        )
        await db.commit()

    session.refund_case_id = rfn_number
    session.otp_verified = False  # reset after refund — next sensitive action needs fresh OTP

    # Update cached transactions status
    cached = getattr(session, "customer_profile", {})
    for t in (cached.get("transactions") or []):
        if t.get("txn_number", "").upper() == txn_upper:
            t["status"] = REFUND_INITIATED

    logger.info(json.dumps({
        "call_id": call_id, "tool": "initiate_refund",
        "transaction_id": transaction_id, "rfn_number": rfn_number,
    }))
    return {
        "success": True,
        "fast_response_key": "refund_initiated",
        "rfn_number": rfn_number,
        "message": f"Refund initiated. Reference number: {rfn_number}. Read this to the customer immediately.",
        "template_vars": {"transaction_id": transaction_id, "rfn_number": rfn_number},
    }


# ── raise_dispute ────────────────────────────────────────────────────────────

async def raise_dispute(transaction_id: str, reason: str, call_id: str) -> dict:
    """
    File a dispute for a completed transaction the customer doesn't recognise
    or didn't receive service for.
    Requires OTP verification. Idempotent — duplicate disputes return fast_response_key.
    """
    session = get_session(call_id)
    if not session or not session.otp_verified:
        return {"success": False, "fast_response_key": "verification_required"}
    if not session.customer_id:
        return {"success": False, "fast_response_key": "verification_required"}

    txn_upper = transaction_id.upper()

    from utils.ref_numbers import next_dsp_number

    async with _db_module.AsyncSessionLocal() as db:
        result = await db.execute(
            text("""
                SELECT id, txn_number, status, amount
                FROM transactions
                WHERE customer_id = :cid AND UPPER(txn_number) = :txn
            """),
            {"cid": _uuid.UUID(session.customer_id), "txn": txn_upper},
        )
        txn_row = result.mappings().first()

    if not txn_row:
        return {"success": False, "fast_response_key": "transaction_not_found"}

    status = txn_row["status"] or ""

    if status == DISPUTED:
        return {"success": False, "fast_response_key": "dispute_duplicate"}
    if status in (CHARGEBACK_INITIATED, CHARGEBACK_WON, CHARGEBACK_LOST):
        return {"success": False, "fast_response_key": "dispute_duplicate"}
    if status == FLAGGED:
        return {"success": False, "fast_response_key": "fraud_review_required"}
    if status in (REFUND_INITIATED, REFUND_PROCESSING):
        return {"success": False, "fast_response_key": "refund_already_initiated"}
    if status == REFUND_COMPLETED:
        return {"success": False, "fast_response_key": "refund_already_completed"}

    amount = float(txn_row["amount"] or 0)
    if amount >= 50000:
        return {"success": False, "fast_response_key": "high_value_manual_required"}

    async with _db_module.AsyncSessionLocal() as db:
        dsp_number = await next_dsp_number(db)

        await db.execute(
            text("UPDATE transactions SET status = :status WHERE id = :id"),
            {"status": DISPUTED, "id": txn_row["id"]},
        )
        await db.execute(
            text("""
                INSERT INTO disputes (dsp_number, transaction_id, customer_id,
                                      reason, status, filed_via, call_id)
                VALUES (:dsp, :tid, :cid, :reason, 'open', 'voice_ai', :call_id)
            """),
            {
                "dsp": dsp_number,
                "tid": txn_row["id"],
                "cid": _uuid.UUID(session.customer_id),
                "reason": reason,
                "call_id": call_id,
            },
        )
        await db.commit()

    # Update session cache
    cached = getattr(session, "customer_profile", {})
    for t in (cached.get("transactions") or []):
        if t.get("txn_number", "").upper() == txn_upper:
            t["status"] = DISPUTED

    logger.info(json.dumps({
        "call_id": call_id, "tool": "raise_dispute",
        "transaction_id": transaction_id, "reason": reason,
        "dsp_number": dsp_number,
    }))
    return {
        "success": True,
        "fast_response_key": "dispute_filed",
        "dsp_number": dsp_number,
        "message": f"Dispute filed. Reference number: {dsp_number}. Read this to the customer immediately.",
        "template_vars": {"transaction_id": transaction_id, "dsp_number": dsp_number},
    }


# ── report_fraud ──────────────────────────────────────────────────────────────

async def report_fraud(transaction_id: str, fraud_type: str, call_id: str) -> dict:
    """
    File a fraud report for an unauthorised transaction.
    Marks the transaction FRAUD_REPORTED, inserts into fraud_cases, triggers account review.
    Requires OTP verification (proves caller owns the account).
    """
    session = get_session(call_id)
    if not session or not session.otp_verified:
        return {"success": False, "fast_response_key": "verification_required"}
    if not session.customer_id:
        return {"success": False, "fast_response_key": "verification_required"}

    txn_upper = transaction_id.upper()

    from utils.ref_numbers import next_fraud_number

    async with _db_module.AsyncSessionLocal() as db:
        result = await db.execute(
            text("""
                SELECT id, txn_number, status
                FROM transactions
                WHERE customer_id = :cid AND UPPER(txn_number) = :txn
            """),
            {"cid": _uuid.UUID(session.customer_id), "txn": txn_upper},
        )
        txn_row = result.mappings().first()

    if not txn_row:
        return {"success": False, "fast_response_key": "transaction_not_found"}

    status = txn_row["status"] or ""

    if status in (FRAUD_REPORTED, FRAUD_CONFIRMED):
        return {"success": False, "fast_response_key": "fraud_already_reported"}
    if status == FRAUD_REVERSED:
        return {"success": False, "fast_response_key": "fraud_transaction_reversed"}

    async with _db_module.AsyncSessionLocal() as db:
        fraud_number = await next_fraud_number(db)

        await db.execute(
            text("UPDATE transactions SET status = :status WHERE id = :id"),
            {"status": FRAUD_REPORTED, "id": txn_row["id"]},
        )
        await db.execute(
            text("""
                INSERT INTO fraud_cases (fraud_number, transaction_id, customer_id,
                                         fraud_type, status, risk_level,
                                         reported_via, call_id)
                VALUES (:fraud_num, :tid, :cid, :ftype, 'under_review', 'high',
                        'voice_ai', :call_id)
            """),
            {
                "fraud_num": fraud_number,
                "tid": txn_row["id"],
                "cid": _uuid.UUID(session.customer_id),
                "ftype": fraud_type,
                "call_id": call_id,
            },
        )
        await db.commit()

    # Update session cache
    cached = getattr(session, "customer_profile", {})
    for t in (cached.get("transactions") or []):
        if t.get("txn_number", "").upper() == txn_upper:
            t["status"] = FRAUD_REPORTED

    logger.info(json.dumps({
        "call_id": call_id, "tool": "report_fraud",
        "transaction_id": transaction_id, "fraud_type": fraud_type,
        "fraud_number": fraud_number,
    }))
    return {
        "success": True,
        "fast_response_key": "fraud_case_opened",
        "fraud_number": fraud_number,
        "message": f"Fraud case opened. Reference number: {fraud_number}. Read this to the customer immediately.",
        "template_vars": {"transaction_id": transaction_id, "fraud_number": fraud_number},
    }


# ── check_payment_status ──────────────────────────────────────────────────────

async def check_payment_status(transaction_id: str, call_id: str) -> dict:
    """
    Return a detailed payment status with SLA context.
    Maps transaction status to a resolution-oriented fast_response_key.
    Used when customer says "my payment is stuck" or "money not credited yet".
    """
    session = get_session(call_id)
    if not session or not session.customer_id:
        return {"success": False, "fast_response_key": "verification_required"}

    txn_upper = transaction_id.upper()
    cached_profile = getattr(session, "customer_profile", None) if session else None
    transactions = cached_profile.get("transactions") or [] if cached_profile else []

    txn = next((t for t in transactions if str(t.get("txn_number", "")).upper() == txn_upper), None)
    if not txn:
        return {"success": False, "fast_response_key": "transaction_not_found"}

    status = txn.get("status", "")
    amount = txn.get("amount", "")
    merchant = txn.get("merchant", "the merchant")
    txn_date = txn.get("txn_date", "")

    # Determine SLA breach — pending for more than 3 hours on same day is abnormal
    from datetime import date as _date
    today = _date.today().isoformat()
    is_today = txn_date == today

    key_map = {
        PENDING:            "payment_processing_delayed" if not is_today else "payment_processing",
        PROCESSING:         "payment_processing",
        FAILED:             "payment_failed_post_debit",
        COMPLETED:          "payment_settled",
        CANCELLED:          "payment_returned",
        EXPIRED:            "payment_returned",
        REFUND_INITIATED:   "payment_returned",
        REFUND_PROCESSING:  "payment_returned",
        REFUND_COMPLETED:   "payment_returned",
        FLAGGED:            "gateway_error",
        KYC_HOLD:           "gateway_error",
    }
    fast_key = key_map.get(status, "gateway_error")

    logger.info(json.dumps({
        "call_id": call_id, "tool": "check_payment_status",
        "transaction_id": transaction_id, "status": status, "key": fast_key,
    }))
    return {
        "success": True,
        "fast_response_key": fast_key,
        "status": status,
        "merchant": merchant,
        "amount": amount,
        "template_vars": {"transaction_id": transaction_id, "merchant": merchant, "amount": amount},
    }


# ── get_account_holds ────────────────────────────────────────────────────────

async def get_account_holds(call_id: str) -> dict:
    """Return active account holds from session cache (loaded at verify_account)."""
    session = get_session(call_id)
    if not session or not session.customer_id:
        return {"success": False, "fast_response_key": "verification_required"}
    profile = getattr(session, "customer_profile", {}) or {}
    holds = profile.get("account_holds") or []
    return {
        "success": True,
        "holds": holds,
        "count": len(holds),
        "has_holds": len(holds) > 0,
    }


# ── get_refund_status ─────────────────────────────────────────────────────────

async def get_refund_status(transaction_id: str | None, call_id: str) -> dict:
    """Return open/in-progress refunds from session cache, optionally filtered by transaction ID."""
    session = get_session(call_id)
    if not session or not session.customer_id:
        return {"success": False, "fast_response_key": "verification_required"}
    profile = getattr(session, "customer_profile", {}) or {}
    refunds = profile.get("open_refunds") or []
    if transaction_id:
        tid = transaction_id.upper()
        refunds = [r for r in refunds if str(r.get("transaction_id", "")).upper() == tid]

    # Fallback: refund row may not exist if it was from a previous demo session
    # (seed re-run orphans old refund rows). If the transaction itself says
    # refund_initiated/refund_processing, surface that so the AI isn't left empty.
    if not refunds and transaction_id:
        txns = profile.get("transactions") or []
        txn = next(
            (t for t in txns if str(t.get("txn_number", "")).upper() == tid),
            None,
        )
        if txn and txn.get("status") in ("refund_initiated", "refund_processing"):
            return {
                "success": True,
                "refunds": [{
                    "transaction_id": txn["txn_number"],
                    "merchant": txn.get("merchant"),
                    "amount": float(txn.get("amount", 0)),
                    "status": "processing",
                    "note": "Refund already in progress for this transaction.",
                }],
                "count": 1,
                "note": (
                    "Refund is in progress. The RFN reference number will be issued "
                    "when the refund clears. Advise the customer to allow 3-5 business days."
                ),
            }

    return {
        "success": True,
        "refunds": refunds,
        "count": len(refunds),
    }


# ── get_dispute_status ────────────────────────────────────────────────────────

async def get_dispute_status(transaction_id: str | None, call_id: str) -> dict:
    """Return open/under-review disputes from session cache, optionally filtered by transaction ID."""
    session = get_session(call_id)
    if not session or not session.customer_id:
        return {"success": False, "fast_response_key": "verification_required"}
    profile = getattr(session, "customer_profile", {}) or {}
    disputes = profile.get("open_disputes") or []
    if transaction_id:
        tid = transaction_id.upper()
        disputes = [d for d in disputes if str(d.get("transaction_id", "")).upper() == tid]
    return {
        "success": True,
        "disputes": disputes,
        "count": len(disputes),
    }


# ── dispatcher ────────────────────────────────────────────────────────────────

async def execute_tool(tool_name: str, args: dict, call_id: str) -> dict:
    """Routes tool_name to the correct implementation."""
    if tool_name == "capture_lead":
        return await capture_lead(
            name=args.get("name", ""),
            email=args.get("email"),
            phone=args.get("phone"),
            company=args.get("company"),
            intent=args.get("intent", "unknown"),
            call_id=call_id,
        )
    elif tool_name == "schedule_demo":
        return await schedule_demo(
            lead_id=args.get("lead_id"),
            name=args.get("name", ""),
            email=args.get("email"),
            preferred_time=args.get("preferred_time", "TBD"),
            call_id=call_id,
            force_slot=args.get("force_slot"),
            user_timezone=args.get("user_timezone", "Asia/Kolkata"),
        )
    elif tool_name == "cancel_demo":
        return await cancel_demo(call_id=call_id)
    elif tool_name == "verify_account":
        return await verify_account(
            phone=args.get("phone", ""),
            call_id=call_id,
        )
    elif tool_name == "lookup_transaction":
        return await lookup_transaction(
            transaction_id=args.get("transaction_id", ""),
            call_id=call_id,
        )
    elif tool_name == "send_otp":
        return await send_otp(call_id=call_id)
    elif tool_name == "verify_otp":
        return await verify_otp(otp_input=args.get("otp_code", ""), call_id=call_id)
    elif tool_name == "unlock_account":
        return await unlock_account(call_id=call_id)
    elif tool_name == "initiate_refund":
        return await initiate_refund(
            transaction_id=args.get("transaction_id", ""),
            call_id=call_id,
        )
    elif tool_name == "raise_dispute":
        return await raise_dispute(
            transaction_id=args.get("transaction_id", ""),
            reason=args.get("reason", "unrecognised_transaction"),
            call_id=call_id,
        )
    elif tool_name == "report_fraud":
        return await report_fraud(
            transaction_id=args.get("transaction_id", ""),
            fraud_type=args.get("fraud_type", "unauthorized_transaction"),
            call_id=call_id,
        )
    elif tool_name == "check_payment_status":
        return await check_payment_status(
            transaction_id=args.get("transaction_id", ""),
            call_id=call_id,
        )
    elif tool_name == "get_account_holds":
        return await get_account_holds(call_id=call_id)
    elif tool_name == "get_refund_status":
        return await get_refund_status(
            transaction_id=args.get("transaction_id"),
            call_id=call_id,
        )
    elif tool_name == "get_dispute_status":
        return await get_dispute_status(
            transaction_id=args.get("transaction_id"),
            call_id=call_id,
        )
    elif tool_name == "escalate_to_human":
        return await escalate_to_human(
            reason=args.get("reason", "customer_request"),
            lead_summary=args.get("lead_summary", ""),
            call_id=call_id,
        )
    else:
        raise ValueError(f"Unknown tool: {tool_name}")
