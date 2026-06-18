"""
Companion AI — real-time support for human agents during escalated calls.

run_mid_call_companion() returns the full elite companion update including:
  - suggested_actions (executable HITL operations with reason/impact/confidence)
  - sentiment_trend (Python-calculated — not LLM)
  - resolution_probability, risk_flags, acw_preview
  - checklist, nudge, next_action, customer_mood, kb_suggestion, insight
"""
import json
import logging
from typing import Optional
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

_client: Optional[AsyncOpenAI] = None


def init_companion_agent(openai_client: AsyncOpenAI) -> None:
    global _client
    _client = openai_client


def _get_mid_call_prompt() -> str:
    try:
        from config_loader import get_config
        p = get_config().companion_mid_call_prompt
        if p:
            return p
    except Exception:
        pass
    return _DEFAULT_MID_CALL_PROMPT


def _get_acw_prompt() -> str:
    try:
        from config_loader import get_config
        p = get_config().companion_acw_prompt
        if p:
            return p
    except Exception:
        pass
    return _DEFAULT_ACW_PROMPT


_DEFAULT_MID_CALL_PROMPT = """
You are an Operational Companion AI helping a specialist resolve a live escalated fintech support call.

WORKFLOW: The specialist IS the final resolution point. They resolve every issue directly.
There is NO fraud team, KYC team, compliance team, or any other internal team to escalate to.
NEVER suggest escalating to another team or department. NEVER suggest escalate_fraud_team.

CRITICAL — NUDGE AND QUICK REPLIES RULE:
The user context includes "LAST CUSTOMER MESSAGE". This is what the customer JUST said this turn.
1. If it is a QUESTION (asking for ref number, status, documents, timeline, policy) → nudge MUST be the
   exact answer using numbers from the financial context (e.g. "Your refund reference is RF-7821,
   initiated 3 days ago — still processing."). quick_replies MUST be 2-3 short answer phrases they can click.
2. If it is a COMPLAINT or STATEMENT → nudge is what the agent should say next to move toward resolution.
3. POST-RESOLUTION: If COMPLETED ACTIONS is non-empty AND the customer's last message is a thank-you,
   acknowledgement, or confirmation that the issue is fixed — nudge MUST be a warm wrap-up line
   (e.g. "Glad we could sort that out, Raj! Is there anything else I can help with today?").
   quick_replies MUST be closing options: ["Is there anything else I can help you with?",
   "Have a great day, take care!", "Glad to help — goodbye!"].
4. If it is NEITHER (short acknowledgement, filler) → nudge can be a forward-driving suggestion.
EVERY TURN: nudge MUST be completely different from PREVIOUS_NUDGE. Never repeat the same phrase.

Analyse the full context and transcript, then return ONLY this JSON (no other text):

{
  "checklist": [
    {"step": "Greet customer and acknowledge the AI handoff", "done": false},
    {"step": "Confirm the specific issue (transaction / hold / account)", "done": false},
    {"step": "Review the financial context and identify the root cause", "done": false},
    {"step": "Approve and execute the fix using the suggested action", "done": false},
    {"step": "Confirm resolution with the customer and close the call", "done": false}
  ],
  "nudge": "If LAST CUSTOMER MESSAGE was a question: exact answer citing ref numbers/amounts from context. If complaint: what agent says next. MUST differ from PREVIOUS_NUDGE. null only if truly nothing to add.",
  "quick_replies": [
    "Short phrase agent speaks verbatim — 4-10 words, cite actual ref/txn numbers when relevant",
    "Alternative answer or acknowledgment option",
    "Follow-up or next-step option"
  ],
  "next_action": "One-line instruction referencing the specific transaction or issue",
  "customer_mood": "calm|frustrated|curious|satisfied|angry",
  "kb_suggestion": {"content": "policy excerpt relevant to this issue", "source": "Document name"},
  "insight": "Key observation grounded in financial context, or null",
  "suggested_actions": [
    {
      "id": "action_name_from_registry",
      "label": "Human-readable label e.g. 'Refund ₹5,400 for TXN-7731'",
      "description": "One line: exactly what this does and why it resolves the customer's issue",
      "reason": "Grounded reason citing the specific txn_number/hold/status from the context",
      "impact": "What changes immediately: account unlocked, refund initiated, hold lifted, etc.",
      "confidence": 0.90,
      "priority": "high|medium|low",
      "risk": "low|medium|high",
      "requires_approval": true,
      "payload": {}
    }
  ],
  "resolution_probability": 0.75,
  "risk_flags": [],
  "acw_preview": {
    "summary": "1-2 sentence summary: issue, root cause identified, action taken",
    "likely_resolution": "resolved|unresolved"
  },
  "documentation_update": {
    "summary": "Updated 1-2 sentence case summary reflecting what has been discussed so far (or null if no change)",
    "action_items": ["Any new follow-up items mentioned in this turn"]
  },
  "resolved_questions": ["questions from open_questions that this turn answered"],
  "new_open_questions": [{"question": "...", "why": "..."}]
}

FINANCIAL CONTEXT SCHEMA:
Use this to identify the specific problem and ground every suggested_action:
- transactions: [{txn_number, merchant, amount, currency, txn_type, status, txn_date}]
  Problematic statuses: failed, pending, processing, flagged, kyc_hold, compliance_hold,
  fraud_reported, fraud_confirmed
- account_holds: [{hold_type, reason, placed_at}]  hold_type: fraud|regulatory|manual|kyc
- open_refunds: [{rfn_number, merchant, amount, status, initiated_at}]
- open_disputes: [{dsp_number, merchant, amount, reason, status, opened_at}]
- active_fraud_cases: [{fraud_number, fraud_type, risk_level, hold_placed_at}]
- account_status: active|locked|suspended|frozen
- fraud_hold_active: true|false
- kyc_status: pending|verified|rejected

TRANSACTION DIAGNOSIS: If a transaction has status=failed/flagged/fraud_reported AND the account
has fraud_hold_active=True — the fix is BOTH remove_fraud_hold AND issue_refund (if the customer
was charged). If account_status=locked, also suggest unlock_account after the hold is cleared.

ACTION REGISTRY — only these exact id strings are valid:
  unlock_account      — sets account_status=active; use after fraud hold is cleared
  remove_fraud_hold   — clears fraud_hold_active; lifts all fraud-type account_holds
  mark_kyc_verified   — sets kyc_status=verified; lifts kyc-type holds
  issue_refund        — initiates refund for a failed/disputed txn; payload: {txn_number}
  reopen_dispute      — opens a dispute for a completed txn; payload: {txn_number, reason}
  reset_2fa           — resets two_fa_last_reset_at (for locked-out customers)
  freeze_account      — sets account_status=frozen (use only for confirmed fraud/safety)

RULES FOR suggested_actions:
- ONLY suggest ids from the registry above — no other values are valid
- NEVER suggest escalate_fraud_team or any variant — it does not exist in this workflow
- Always reference the exact txn_number, rfn_number, or dsp_number from the context in payload and reason
- issue_refund: only valid if transaction status is failed/flagged (not already refund_initiated)
- remove_fraud_hold: only if fraud_hold_active=True OR account_holds has a fraud-type hold
- mark_kyc_verified: only if kyc_status is pending/rejected AND documents confirmed on call
- unlock_account: only after remove_fraud_hold is done, OR if account is locked without a fraud hold
- Return [] if the specialist has already resolved the issue or no action is needed yet
- Max 2 suggested_actions per response; list most urgent first
- NEVER re-suggest any action that appears in the completed_actions list

RULES FOR risk_flags (return any that apply):
  "repeat_complaint"       — same issue mentioned in a previous call
  "long_call"              — many turns without resolution
  "compliance_mention"     — customer mentioned legal/complaint/regulatory/ombudsman
  "unresolved_ai_attempt"  — AI tried and failed to resolve this before escalation
  "active_hold_detected"   — account_hold that has not been addressed yet
  "fraud_case_open"        — active fraud case under review

Infer checklist done-state from what is visible in the transcript.
resolution_probability: 0.0 = still diagnosing, 1.0 = fully resolved.
"""

_DEFAULT_ACW_PROMPT = """
The call has ended. Generate the After Call Work summary from the full transcript.
Return ONLY this JSON (no other text):

{
  "summary": "3-5 sentences. MUST include: (1) what the customer called about, (2) root cause identified (specific transaction numbers, fraud case numbers, hold types — cite them verbatim), (3) what the specialist did to resolve it, (4) final outcome confirmed by the customer. Example: 'Raj Patel called regarding an inability to make payments due to a fraud hold on his account. The hold was linked to transaction TXN-9901 (₹18,000, unknown vendor) under fraud case FRAUD-202605-0001. The specialist confirmed the unauthorized transaction, removed the fraud hold, and initiated a refund of ₹18,000. Raj confirmed the account was accessible and the refund was visible. Case resolved.'",
  "resolution": "resolved|escalated|unresolved",
  "action_items": ["list of follow-up actions if any — e.g. 'Monitor refund RFN-XXXXXX for 3-5 business days'"],
  "crm_fields": {
    "notes": "One sentence with specific references: issue, transaction/case IDs, action taken, outcome."
  },
  "coaching_note": "one sentence coaching note for the agent"
}
"""

# Mood rank for trend calculation — higher = better
_MOOD_RANK = {
    "angry": 0,
    "frustrated": 1,
    "calm": 2,
    "curious": 3,
    "satisfied": 4,
}


async def _fetch_kb_for_companion(query: str) -> Optional[dict]:
    """ChromaDB search — top match only, relevance threshold 0.28 (prevents noise)."""
    if not query:
        return None
    try:
        from knowledge.kb_manager import search_kb
        hits = await search_kb(query, n_results=1)
        if hits and hits[0].get("relevance", 0.0) > 0.28:
            return {
                "content": hits[0].get("content", ""),
                "source":  hits[0].get("source", "KB"),
            }
    except Exception:
        pass
    return None


async def run_mid_call_companion(
    transcript: list[dict],
    customer: dict,
    handoff_bundle: Optional[dict] = None,
    workflow_type: Optional[str] = None,
    previous_mood: Optional[str] = None,
    completed_actions: Optional[set] = None,
    previous_nudge: Optional[str] = None,
) -> dict:
    if not _client:
        return _default_mid_call_response()

    messages = [{"role": "system", "content": _get_mid_call_prompt()}]

    context_parts = []

    # Workflow type — drives which actions companion may suggest
    if workflow_type:
        context_parts.append(f"WORKFLOW: {workflow_type}")

    # Completed actions — companion must not re-suggest these
    if completed_actions:
        context_parts.append(
            f"COMPLETED ACTIONS THIS CALL (DO NOT suggest again): {', '.join(completed_actions)}"
        )

    # Customer context from handoff bundle
    # All fintech data lives under handoff_bundle["lead"] (serialized by EscalationPacket.to_dict)
    if handoff_bundle:
        lead = handoff_bundle.get("lead", {}) or {}

        name = lead.get("name")
        if name:
            context_parts.append(f"CUSTOMER: {name}")

        account_type = lead.get("account_type")
        account_status = lead.get("account_status")
        kyc_status = lead.get("kyc_status")
        fraud_hold = lead.get("fraud_hold_active", False)
        # If remove_fraud_hold was executed this call, the hold is now cleared —
        # suppress the stale ACTIVE flag so the companion doesn't keep nudging about it.
        if completed_actions and "remove_fraud_hold" in completed_actions:
            fraud_hold = False
        if account_type:
            status_note = f" (status: {account_status})" if account_status and account_status != "active" else ""
            context_parts.append(f"Account type: {account_type}{status_note}")
        if kyc_status and kyc_status != "verified":
            context_parts.append(f"KYC status: {kyc_status}")
        if fraud_hold:
            context_parts.append("Fraud hold: ACTIVE")

        intent = lead.get("intent") or handoff_bundle.get("intent")
        if intent:
            context_parts.append(f"Detected intent: {intent.replace('_', ' ')}")
        reason = handoff_bundle.get("reason")
        if reason:
            context_parts.append(f"Escalation reason: {reason}")
        cid = handoff_bundle.get("customer_id")
        if cid:
            context_parts.append(f"customer_id (for payload): {cid}")

        # Financial context — grounded from normalized tables
        transactions = lead.get("transactions") or []
        if transactions:
            txn_lines = [
                f"  {t.get('txn_number','?')}: {t.get('merchant','?')} "
                f"₹{t.get('amount','?')} {t.get('txn_type','?')} "
                f"status={t.get('status','?')} date={t.get('txn_date','?')}"
                for t in transactions[:5]
            ]
            context_parts.append("TRANSACTIONS:\n" + "\n".join(txn_lines))

        holds = lead.get("account_holds") or []
        if holds:
            hold_lines = [
                f"  {h.get('hold_type','?')}: {h.get('reason','no reason given')}"
                for h in holds
            ]
            context_parts.append("ACTIVE ACCOUNT HOLDS:\n" + "\n".join(hold_lines))

        refunds = lead.get("open_refunds") or []
        if refunds:
            ref_lines = [
                f"  {r.get('rfn_number','?')}: {r.get('merchant','?')} "
                f"₹{r.get('amount','?')} status={r.get('status','?')} "
                f"for txn={r.get('transaction_id','?')}"
                for r in refunds
            ]
            context_parts.append("IN-PROGRESS REFUNDS:\n" + "\n".join(ref_lines))

        disputes = lead.get("open_disputes") or []
        if disputes:
            dsp_lines = [
                f"  {d.get('dsp_number','?')}: {d.get('merchant','?')} "
                f"₹{d.get('amount','?')} reason={d.get('reason','?')} "
                f"status={d.get('status','?')} txn={d.get('transaction_id','?')}"
                for d in disputes
            ]
            context_parts.append("OPEN DISPUTES:\n" + "\n".join(dsp_lines))

        fraud_cases = lead.get("active_fraud_cases") or []
        if fraud_cases:
            fc_lines = [
                f"  {f.get('fraud_number','?')}: {f.get('fraud_type','?')} "
                f"risk={f.get('risk_level','?')} txn={f.get('transaction_id','?')}"
                for f in fraud_cases
            ]
            context_parts.append("ACTIVE FRAUD CASES:\n" + "\n".join(fc_lines))

    # Extract last customer message — used for KB query AND injected explicitly for nudge generation
    last_customer_text = next(
        (
            l.get("text") or l.get("content", "")
            for l in reversed(transcript)
            if l.get("speaker") in ("customer", "user") and (l.get("text") or l.get("content"))
        ),
        None,
    )

    # Inject last customer turn as explicit anchor — this is what nudge/quick_replies MUST respond to
    if last_customer_text:
        context_parts.append(
            f"LAST CUSTOMER MESSAGE (nudge and quick_replies MUST directly address this): {last_customer_text}"
        )

    # Nudge dedup — hard constraint: LLM must generate completely different content
    if previous_nudge:
        context_parts.append(
            f"PREVIOUS_NUDGE (FORBIDDEN — never repeat any phrase from this): {previous_nudge}"
        )

    if context_parts:
        messages.append({"role": "user", "content": "\n".join(context_parts)})

    # Build an enriched query: call reason + last utterance (boosts KB relevance)
    kb_query = last_customer_text
    if handoff_bundle:
        lead = handoff_bundle.get("lead", {}) or {}
        intent = lead.get("intent") or handoff_bundle.get("reason") or ""
        if intent and last_customer_text:
            kb_query = f"{intent}: {last_customer_text}"
        elif intent:
            kb_query = intent
    real_kb_hit = await _fetch_kb_for_companion(kb_query)

    transcript_text = _format_transcript(transcript)
    kb_block = (
        f"\n\nKB DOCUMENT (cite verbatim in kb_suggestion):\n"
        f"Source: {real_kb_hit['source']}\nContent: {real_kb_hit['content']}"
        if real_kb_hit else
        "\n\nKB DOCUMENT: No high-relevance match — set kb_suggestion to null."
    )
    messages.append({
        "role": "user",
        "content": f"TRANSCRIPT:\n{transcript_text}{kb_block}\n\nGenerate companion update now.",
    })

    try:
        resp = await _client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.4,
            max_tokens=850,
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content or "{}"
        data = json.loads(raw)
        result = _normalize_mid_call(data)
        if real_kb_hit:
            result["kb_suggestion"] = real_kb_hit
    except Exception:
        result = _default_mid_call_response()

    # Calculate sentiment_trend in Python (not LLM) — avoids prompt injection drift
    current_mood = result.get("customer_mood", "calm")
    result["sentiment_trend"] = _calc_sentiment_trend(current_mood, previous_mood)

    return result


def _calc_sentiment_trend(current: str, previous: Optional[str]) -> str:
    if not previous or current == previous:
        return "stable"
    curr_rank = _MOOD_RANK.get(current, 2)
    prev_rank = _MOOD_RANK.get(previous, 2)
    if curr_rank > prev_rank:
        return "improving"
    if curr_rank < prev_rank:
        return "declining"
    return "stable"


async def run_acw_agent(
    transcript: list[dict],
    customer: dict,
    call_id: str,
    handoff_bundle: Optional[dict] = None,
) -> dict:
    if not _client:
        return _default_acw_response()

    messages = [{"role": "system", "content": _get_acw_prompt()}]

    # Inject financial context from handoff bundle so ACW can cite TXN/case numbers
    if handoff_bundle:
        lead = handoff_bundle.get("lead", {}) or {}
        ctx_lines = []
        name = lead.get("name")
        if name:
            ctx_lines.append(f"Customer: {name}")
        txns = lead.get("transactions") or []
        for t in txns[:3]:
            ctx_lines.append(
                f"Transaction: {t.get('txn_number','?')} — {t.get('merchant','?')} "
                f"₹{t.get('amount','?')} status={t.get('status','?')}"
            )
        fraud_cases = lead.get("active_fraud_cases") or []
        for fc in fraud_cases:
            ctx_lines.append(
                f"Fraud case: {fc.get('fraud_number','?')} type={fc.get('fraud_type','?')}"
            )
        holds = lead.get("account_holds") or []
        for h in holds:
            ctx_lines.append(f"Account hold: {h.get('hold_type','?')} — {h.get('reason','')}")
        refunds = lead.get("open_refunds") or []
        for r in refunds:
            ctx_lines.append(
                f"Refund: {r.get('rfn_number','?')} — ₹{r.get('amount','?')} "
                f"status={r.get('status','?')} for txn={r.get('transaction_id','?')}"
            )
        if ctx_lines:
            messages.append({"role": "user", "content": "FINANCIAL CONTEXT:\n" + "\n".join(ctx_lines)})

    messages.append({"role": "user", "content": f"Call ID: {call_id}"})
    transcript_text = _format_transcript(transcript)
    messages.append({
        "role": "user",
        "content": f"FULL TRANSCRIPT:\n{transcript_text}\n\nGenerate ACW summary now.",
    })

    try:
        resp = await _client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.3,
            max_tokens=500,
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content or "{}"
        data = json.loads(raw)
        return _normalize_acw(data)
    except Exception:
        return _default_acw_response()


def _format_transcript(transcript: list[dict]) -> str:
    lines = []
    for entry in transcript:
        speaker = entry.get("speaker", "unknown")
        text = entry.get("text", entry.get("content", ""))
        lines.append(f"[{speaker}]: {text}")
    return "\n".join(lines) if lines else "(empty transcript)"


def _normalize_mid_call(data: dict) -> dict:
    # Validate suggested_actions — remove entries with bad ids
    from orchestration.action_registry import ACTION_REGISTRY
    raw_actions = data.get("suggested_actions") or []
    valid_actions = []
    for a in raw_actions:
        if not isinstance(a, dict):
            continue
        if a.get("id") not in ACTION_REGISTRY:
            continue
        valid_actions.append({
            "id":               a.get("id"),
            "label":            a.get("label", a.get("id", "").replace("_", " ").title()),
            "description":      a.get("description", ""),
            "reason":           a.get("reason", ""),
            "impact":           a.get("impact", ""),
            "confidence":       float(a.get("confidence", 0.7)),
            "priority":         a.get("priority", "medium"),
            "risk":             a.get("risk", "medium"),
            "requires_approval": True,
            "payload":          a.get("payload") or {},
        })

    acw_raw = data.get("acw_preview") or {}

    raw_qr = data.get("quick_replies") or []
    quick_replies = [r for r in raw_qr if isinstance(r, str) and r.strip()][:3]

    return {
        "checklist":              data.get("checklist", _default_checklist()),
        "quick_replies":          quick_replies,
        "nudge":                  data.get("nudge"),
        "next_action":            data.get("next_action", "Listen and assist the customer"),
        "customer_mood":          data.get("customer_mood", "calm"),
        "kb_suggestion":          data.get("kb_suggestion"),
        "insight":                data.get("insight"),
        "suggested_actions":      valid_actions,
        "resolution_probability": float(data.get("resolution_probability", 0.5)),
        "risk_flags":             [f for f in (data.get("risk_flags") or []) if isinstance(f, str)],
        "acw_preview": {
            "summary":            acw_raw.get("summary", ""),
            "likely_resolution":  acw_raw.get("likely_resolution", "unresolved"),
        },
        # Live documentation updates — merged into session._live_documentation by ws_agent
        "documentation_update":  _normalize_doc_update(data.get("documentation_update")),
        "resolved_questions":    [q for q in (data.get("resolved_questions") or []) if isinstance(q, str)],
        "new_open_questions":    _normalize_open_questions(data.get("new_open_questions") or []),
        # sentiment_trend is injected by Python after _normalize_mid_call
        "sentiment_trend": "stable",
    }


def _normalize_doc_update(raw) -> Optional[dict]:
    if not isinstance(raw, dict):
        return None
    summary = raw.get("summary")
    items   = [i for i in (raw.get("action_items") or []) if isinstance(i, str) and i.strip()]
    if not summary and not items:
        return None
    return {"summary": summary, "action_items": items}


def _normalize_open_questions(raw: list) -> list[dict]:
    result = []
    for q in raw[:2]:
        if isinstance(q, dict):
            result.append({"question": q.get("question", ""), "why": q.get("why", "")})
        elif isinstance(q, str) and q.strip():
            result.append({"question": q, "why": ""})
    return result


def _normalize_acw(data: dict) -> dict:
    return {
        "summary":       data.get("summary", "Call completed."),
        "resolution":    data.get("resolution", "unresolved"),
        "action_items":  data.get("action_items", []),
        "crm_fields":    data.get("crm_fields", {}),
        "coaching_note": data.get("coaching_note", ""),
    }


def _default_checklist() -> list[dict]:
    return [
        {"step": "Greet customer and acknowledge the Voice AI handoff", "done": False},
        {"step": "Confirm the issue they are facing", "done": False},
        {"step": "Verify customer identity if not already done", "done": False},
        {"step": "Resolve or escalate based on issue type", "done": False},
        {"step": "Confirm resolution and close the interaction", "done": False},
    ]


def _default_mid_call_response() -> dict:
    return {
        "checklist":              _default_checklist(),
        "nudge":                  None,
        "next_action":            "Greet the customer and ask how you can help",
        "customer_mood":          "calm",
        "kb_suggestion":          None,
        "insight":                None,
        "quick_replies":          [],
        "suggested_actions":      [],
        "resolution_probability": 0.5,
        "risk_flags":             [],
        "acw_preview":            {"summary": "", "likely_resolution": "unresolved"},
        "documentation_update":   None,
        "resolved_questions":     [],
        "new_open_questions":     [],
        "sentiment_trend":        "stable",
    }


def _default_acw_response() -> dict:
    return {
        "summary":       "Call completed. Details unavailable.",
        "resolution":    "unresolved",
        "action_items":  [],
        "crm_fields":    {},
        "coaching_note": "",
    }
