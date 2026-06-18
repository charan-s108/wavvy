"""
Case Intelligence Engine — runs on escalation as a background task.

Three-layer output:
  1. Deterministic (no LLM): known_facts, timeline, data_inconsistencies, risk
  2. LLM (single gpt-4o-mini call): what_happened, open_questions, recommended_resolution
  3. Initial live_documentation: written to session._live_documentation

Sends a "case_investigation" WS event. The agent console renders this in the
HandoffCard before the agent answers — no polling, no delay.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

_client: Optional[AsyncOpenAI] = None

FAILED_STATUSES = {"failed", "flagged", "kyc_hold", "compliance_hold", "fraud_reported", "fraud_confirmed"}


def init_investigation_agent(openai_client: AsyncOpenAI) -> None:
    global _client
    _client = openai_client


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def run_case_investigation(ws, session, call_id: str) -> None:
    """
    Run after escalation is delivered to the agent. Sends case_investigation event.
    Deterministic layer is synchronous; LLM layer is one async call.
    """
    profile = _load_profile(session)

    esc_type        = _classify_escalation_type(session)
    known_facts     = _extract_known_facts(session, profile)
    timeline        = _reconstruct_timeline(session, profile)
    inconsistencies = _detect_data_inconsistencies(profile)
    risk            = _compute_risk(profile, inconsistencies)

    llm_result = await _generate_case_narrative(
        session, profile, known_facts, timeline, inconsistencies, esc_type
    )

    live_doc = _build_initial_documentation(session, profile, known_facts, llm_result)
    session._live_documentation = live_doc

    payload = {
        "type":                   "case_investigation",
        "escalation_type":        esc_type,
        "case_status":            "investigation_complete",
        "what_happened":          llm_result.get("what_happened", ""),
        "known_facts":            known_facts,
        "open_questions":         llm_result.get("open_questions", []),
        "data_inconsistencies":   inconsistencies,
        "timeline":               timeline,
        "risk":                   risk,
        "recommended_resolution": llm_result.get("recommended_resolution", ""),
        "live_documentation":     live_doc,
    }

    try:
        await ws.send_text(json.dumps(payload))
        logger.info("[%s] Case investigation delivered (type=%s, inconsistencies=%d)",
                    call_id, esc_type, len(inconsistencies))
    except Exception as exc:
        logger.error("[%s] Failed to send case_investigation: %s", call_id, exc)


# ---------------------------------------------------------------------------
# Deterministic layer
# ---------------------------------------------------------------------------

def _load_profile(session) -> dict:
    return getattr(session, "customer_profile", {}) or {}


def _classify_escalation_type(session) -> str:
    from models.escalation_type import classify_escalation_type, EscalationType
    return classify_escalation_type(session).value


def _extract_known_facts(session, profile: dict) -> list[dict]:
    facts = []

    if getattr(session, "otp_verified", False):
        facts.append({"fact": "Identity verified via OTP", "source": "AI workflow"})

    acct_status = profile.get("account_status")
    acct_type   = profile.get("account_type")
    if acct_type:
        label = acct_type.title()
        if acct_status and acct_status != "active":
            label += f" (status: {acct_status})"
        facts.append({"fact": f"Account type: {label}", "source": "customer profile"})

    if acct_status and acct_status != "active":
        facts.append({"fact": f"Account status: {acct_status}", "source": "customer profile"})

    kyc = profile.get("kyc_status")
    if kyc and kyc != "verified":
        facts.append({"fact": f"KYC status: {kyc}", "source": "customer profile"})

    if profile.get("fraud_hold_active"):
        facts.append({"fact": "Fraud hold: ACTIVE", "source": "customer profile"})

    # Most problematic transaction
    txns = profile.get("transactions") or []
    problem_txn = _most_problematic_txn(txns)
    if problem_txn:
        t = problem_txn
        facts.append({
            "fact": (f"Transaction {t.get('txn_number','?')}: {t.get('status','?').upper()} — "
                     f"₹{t.get('amount','?')} {t.get('merchant','')}"),
            "source": "transaction table",
        })

    # Open refunds
    for rfn in (profile.get("open_refunds") or []):
        facts.append({
            "fact": (f"Refund {rfn.get('rfn_number','?')} {rfn.get('status','initiated')} "
                     f"— ₹{rfn.get('amount','?')}"),
            "source": "refund table",
        })

    # Active holds
    for hold in (profile.get("account_holds") or []):
        facts.append({
            "fact": f"Account hold: {hold.get('hold_type','?')} — {hold.get('reason','no reason given')}",
            "source": "account holds",
        })

    # Workflow steps that represent completed verifications
    wf = getattr(session, "workflow", None)
    if wf and hasattr(wf, "steps_taken"):
        STEP_FACTS = {
            "verify_account": "Account located in CRM",
            "check_transaction_status": "Transaction status retrieved",
        }
        seen = set()
        for step in wf.steps_taken:
            label = STEP_FACTS.get(step.get("step", ""))
            if label and label not in seen:
                seen.add(label)
                facts.append({"fact": label, "source": "AI workflow"})

    return facts


def _reconstruct_timeline(session, profile: dict) -> list[dict]:
    events: list[tuple[datetime, str]] = []

    now = datetime.now(timezone.utc)

    # Pre-call: transactions
    for txn in (profile.get("transactions") or []):
        ts = _parse_ts(txn.get("txn_date"))
        if ts:
            merchant = txn.get("merchant", "")
            amount   = txn.get("amount", "?")
            status   = txn.get("status", "?")
            txn_num  = txn.get("txn_number", "?")
            events.append((ts, f"Payment {status} — {txn_num} ₹{amount} {merchant}".strip()))

    # Pre-call: refunds
    for rfn in (profile.get("open_refunds") or []):
        ts = _parse_ts(rfn.get("initiated_at"))
        if ts:
            events.append((ts, f"Refund {rfn.get('rfn_number','?')} initiated — ₹{rfn.get('amount','?')}"))

    # Pre-call: disputes
    for dsp in (profile.get("open_disputes") or []):
        ts = _parse_ts(dsp.get("opened_at"))
        if ts:
            events.append((ts, f"Dispute {dsp.get('dsp_number','?')} opened — {dsp.get('reason','')}"))

    # Call start
    started_at = getattr(session, "started_at", None)
    if started_at:
        if not started_at.tzinfo:
            started_at = started_at.replace(tzinfo=timezone.utc)
        events.append((started_at, "Customer called"))

    # Workflow steps
    STEP_LABELS = {
        "verify_account":          "AI located customer account",
        "send_otp":                "AI sent OTP to customer",
        "verify_otp":              "AI verified identity via OTP",
        "check_transaction_status":"AI retrieved transaction status",
        "initiate_refund":         "AI initiated refund",
        "unlock_account":          "AI unlocked account",
    }
    wf = getattr(session, "workflow", None)
    if wf and hasattr(wf, "steps_taken"):
        for step in wf.steps_taken:
            ts = _parse_ts(step.get("ts"))
            label = STEP_LABELS.get(step.get("step", ""))
            if ts and label:
                events.append((ts, label))

    # Escalation (now)
    events.append((now, "Escalated to human agent"))

    # Sort, deduplicate labels within 1 second
    events.sort(key=lambda e: e[0])
    result = []
    for ts, label in events:
        result.append({"ts": _friendly_ts(ts, now), "event": label})

    return result


def _detect_data_inconsistencies(profile: dict) -> list[dict]:
    issues = []
    txns     = profile.get("transactions") or []
    refunds  = profile.get("open_refunds") or []
    holds    = profile.get("account_holds") or []
    disputes = profile.get("open_disputes") or []

    # 1. Duplicate refund risk: failed txn already has a refund in progress
    failed_ids = {
        (t.get("txn_number") or t.get("id") or "").lower()
        for t in txns if t.get("status") in FAILED_STATUSES
    }
    for rfn in refunds:
        linked_txn = (rfn.get("transaction_id") or rfn.get("txn_number") or "").lower()
        if linked_txn and linked_txn in failed_ids:
            issues.append({
                "severity": "HIGH",
                "type":     "duplicate_refund_risk",
                "headline": f"Refund {rfn.get('rfn_number','?')} already exists for this transaction",
                "detail":   "Initiating another refund will create a duplicate payout. Confirm the existing refund status first.",
                "evidence": {
                    "existing_refund":  rfn.get("rfn_number"),
                    "refund_status":    rfn.get("status"),
                    "refund_amount":    rfn.get("amount"),
                },
            })

    # 2. Account "active" but holds exist
    acct_status = profile.get("account_status", "")
    if acct_status == "active" and holds:
        hold_types = [h.get("hold_type", "?") for h in holds]
        issues.append({
            "severity": "MEDIUM",
            "type":     "hold_status_mismatch",
            "headline": f"Account shows 'active' but {len(holds)} hold(s) are present",
            "detail":   "System state may be inconsistent. Verify before making changes.",
            "evidence": {"hold_types": hold_types},
        })

    # 3. KYC pending/rejected but account active
    kyc = profile.get("kyc_status", "")
    if kyc in ("pending", "rejected") and acct_status == "active":
        issues.append({
            "severity": "MEDIUM",
            "type":     "kyc_mismatch",
            "headline": f"KYC is '{kyc}' but account is active",
            "detail":   "Some operations may be restricted. Confirm KYC status with customer.",
            "evidence": {"kyc_status": kyc},
        })

    # 4. Fraud hold active but no fraud case on record
    if profile.get("fraud_hold_active") and not (profile.get("active_fraud_cases") or []):
        issues.append({
            "severity": "LOW",
            "type":     "orphaned_fraud_hold",
            "headline": "Fraud hold is active but no fraud case found",
            "detail":   "The hold may be stale. Review before removing.",
            "evidence": {},
        })

    # 5. Open dispute on an already-refunded transaction
    refunded_txn_ids = {
        (r.get("transaction_id") or "").lower()
        for r in refunds
        if r.get("status") in ("completed", "processing", "initiated")
    }
    for dsp in disputes:
        dsp_txn = (dsp.get("transaction_id") or "").lower()
        if dsp_txn and dsp_txn in refunded_txn_ids:
            issues.append({
                "severity": "MEDIUM",
                "type":     "dispute_on_refunded_txn",
                "headline": f"Dispute {dsp.get('dsp_number','?')} is open on a transaction with an active refund",
                "detail":   "Resolution may already be in progress. Closing the dispute may be appropriate.",
                "evidence": {
                    "dispute": dsp.get("dsp_number"),
                    "txn_id":  dsp.get("transaction_id"),
                },
            })

    return issues


def _compute_risk(profile: dict, inconsistencies: list[dict]) -> str:
    high_issues = sum(1 for i in inconsistencies if i.get("severity") == "HIGH")
    if high_issues > 0:
        return "HIGH"
    fraud_hold = profile.get("fraud_hold_active", False)
    fraud_cases = profile.get("active_fraud_cases") or []
    acct_status = profile.get("account_status", "active")
    if fraud_hold or fraud_cases or acct_status in ("locked", "suspended", "frozen"):
        return "HIGH"
    medium_issues = sum(1 for i in inconsistencies if i.get("severity") == "MEDIUM")
    if medium_issues > 0:
        return "MEDIUM"
    return "LOW"


# ---------------------------------------------------------------------------
# LLM layer — single call, structured output
# ---------------------------------------------------------------------------

_NARRATIVE_PROMPT = """
You are a case analyst for a fintech support platform. An AI voice agent escalated a customer
call to a human specialist. Analyse the case data and return structured JSON.

Return ONLY valid JSON with these exact keys:
{
  "what_happened": "2-3 sentence plain-English summary of the customer's situation and why they called. Reference specific transaction numbers, amounts, merchants where available.",
  "open_questions": [
    {"question": "...", "why": "..."}
  ],
  "recommended_resolution": "1-2 sentences: what the specialist should do. Reference specific data. Do NOT stage actions or use APPROVE/EXECUTE framing — this is guidance, not a button."
}

RULES:
- open_questions: 1-2 items max. Only questions that cannot be answered from the data alone.
- what_happened: factual, specific, no jargon.
- recommended_resolution: guidance only, grounded in the data. Never say "click" or "approve".
- If data_inconsistencies contains HIGH severity items, the recommended_resolution must reference them.
"""


async def _generate_case_narrative(
    session, profile: dict,
    known_facts: list[dict],
    timeline: list[dict],
    inconsistencies: list[dict],
    esc_type: str,
) -> dict:
    if not _client:
        return _fallback_narrative(session, profile, known_facts)

    orch_state = getattr(session, "orchestrator_state", None)
    call_reason = (getattr(orch_state, "escalation_call_reason", "") or
                   getattr(session, "escalation_reason", "") or "")

    context_lines = [
        f"ESCALATION TYPE: {esc_type.upper()}",
    ]
    if call_reason:
        context_lines.append(f"CALL REASON: {call_reason}")

    context_lines.append("\nKNOWN FACTS:")
    for f in known_facts:
        context_lines.append(f"  - {f['fact']} (source: {f['source']})")

    context_lines.append("\nTIMELINE (chronological):")
    for ev in timeline:
        context_lines.append(f"  {ev['ts']}: {ev['event']}")

    if inconsistencies:
        context_lines.append("\nDATA INCONSISTENCIES (CRITICAL — reference in recommendation if HIGH):")
        for inc in inconsistencies:
            context_lines.append(
                f"  [{inc['severity']}] {inc['headline']} — {inc['detail']}"
            )

    # Include the full voice conversation so the LLM has real context
    history = getattr(session, "conversation_history", []) or []
    voice_lines = []
    for m in history:
        role = m.get("role", "")
        content = m.get("content", "") or ""
        if not content or role == "system":
            continue
        speaker = "Customer" if role == "user" else "Fin"
        voice_lines.append(f"  {speaker}: {content[:200]}")
    if voice_lines:
        context_lines.append("\nVOICE CONVERSATION (summarised):")
        context_lines.extend(voice_lines[-20:])  # last 20 turns max
    else:
        last_user_msg = getattr(session, "_last_transcript", "") or ""
        if last_user_msg:
            context_lines.append(f"\nLAST CUSTOMER MESSAGE: {last_user_msg}")

    try:
        resp = await _client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": _NARRATIVE_PROMPT},
                {"role": "user", "content": "\n".join(context_lines)},
            ],
            temperature=0.3,
            max_tokens=400,
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content or "{}"
        data = json.loads(raw)
        return {
            "what_happened":          data.get("what_happened", ""),
            "open_questions":         _normalize_questions(data.get("open_questions", [])),
            "recommended_resolution": data.get("recommended_resolution", ""),
        }
    except Exception as exc:
        logger.error("Case narrative LLM call failed: %s", exc)
        return _fallback_narrative(session, profile, known_facts)


def _normalize_questions(raw: list) -> list[dict]:
    result = []
    for q in raw[:2]:
        if isinstance(q, dict):
            result.append({"question": q.get("question", ""), "why": q.get("why", "")})
        elif isinstance(q, str):
            result.append({"question": q, "why": ""})
    return result


def _fallback_narrative(session, profile: dict, known_facts: list[dict]) -> dict:
    reason = getattr(session, "escalation_reason", "") or "call escalated to specialist"
    name = profile.get("first_name") or profile.get("name") or "The customer"
    return {
        "what_happened":          f"{name} called and {reason}. Review the known facts above for details.",
        "open_questions":         [],
        "recommended_resolution": "Review the known facts and data inconsistencies above, then address the customer's concern directly.",
    }


# ---------------------------------------------------------------------------
# Live documentation seed
# ---------------------------------------------------------------------------

def _build_initial_documentation(
    session, profile: dict, known_facts: list[dict], llm_result: dict
) -> dict:
    name = profile.get("first_name") or profile.get("name") or "Customer"
    summary = llm_result.get("what_happened", "")
    if not summary:
        reason = getattr(session, "escalation_reason", "") or "escalated to human agent"
        summary = f"{name} called and {reason}."

    orch_state = getattr(session, "orchestrator_state", None)
    notes_parts = ["Escalated from Voice AI."]
    if getattr(session, "otp_verified", False):
        notes_parts.append("Identity verified.")
    call_reason = getattr(orch_state, "escalation_call_reason", "") or ""
    if call_reason:
        notes_parts.append(f"Reason: {call_reason}.")

    return {
        "summary":      summary,
        "resolution":   "pending",
        "action_items": [],
        "crm_fields":   {"notes": " ".join(notes_parts)},
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _most_problematic_txn(txns: list[dict]) -> dict | None:
    STATUS_PRIORITY = {s: 0 for s in FAILED_STATUSES}
    STATUS_PRIORITY.update({"processing": 1, "pending": 2})
    best = None
    best_priority = 999
    for t in txns:
        p = STATUS_PRIORITY.get(t.get("status", ""), 999)
        if p < best_priority:
            best_priority = p
            best = t
    return best if best_priority < 3 else None


def _parse_ts(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if not value.tzinfo:
            return value.replace(tzinfo=timezone.utc)
        return value
    if isinstance(value, str):
        for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z",
                    "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ",
                    "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(value.rstrip("Z"), fmt.rstrip("Z"))
                return dt.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
    return None


def _friendly_ts(ts: datetime, now: datetime) -> str:
    if not ts.tzinfo:
        ts = ts.replace(tzinfo=timezone.utc)
    if not now.tzinfo:
        now = now.replace(tzinfo=timezone.utc)
    diff = now - ts
    time_str = ts.strftime("%H:%M")
    if diff < timedelta(minutes=2):
        return f"Just now"
    if diff < timedelta(hours=23):
        return f"Today {time_str}"
    days = diff.days
    if days == 1:
        return f"Yesterday {time_str}"
    if days < 7:
        return f"{days} days ago {time_str}"
    return ts.strftime("%b %d %H:%M")
