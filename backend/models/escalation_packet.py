"""
Standard escalation payload for Agent Desktop.
Only format used system-wide — never a raw dict.
Completeness guard: auto-fills missing fields from session before emit.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)


@dataclass
class EscalationPacket:
    call_id: str
    lead_id: str | None                  # set if capture_lead ran before escalation
    name: str | None                     # prospect name
    email: str | None                    # prospect email (masked: ar***@company.com)
    phone: str | None                    # prospect phone (masked: ***210)
    company: str | None                  # prospect company
    intent: str                          # Intent.value — what they called about
    workflow_summary: str                # WorkflowSummary.to_text()
    last_user_message: str
    key_interests: list[str]             # topics discussed: ["pricing", "integration", "vs_vapi"]
    sentiment_status: str | None         # "positive" | "neutral" | "negative"
    transcript_excerpt: list[dict]       # last 10 turns [{role, content}]
    call_duration_sec: int               # seconds elapsed at escalation moment
    last_tool_attempted: str | None      # name of last tool called (even if failed)
    failure_reason: str | None           # "customer_request" | "tool_failure" | "sentiment" | "unknown_threshold"
    account_type: str | None = None      # from customer_profile (Fin flow)
    account_status: str | None = None    # active | locked | frozen | suspended
    kyc_status: str | None = None        # pending | verified | rejected
    fraud_hold_active: bool = False
    transactions: list = field(default_factory=list)       # from customer_profile
    account_holds: list = field(default_factory=list)      # active holds (hold_type, reason)
    open_refunds: list = field(default_factory=list)       # in-progress refunds
    open_disputes: list = field(default_factory=list)      # non-terminal disputes
    active_fraud_cases: list = field(default_factory=list) # fraud cases under review

    def to_dict(self) -> dict:
        return {
            "call_id":            self.call_id,
            "reason":             self.failure_reason,
            # Nested lead object — used by CRMCard and companion_agent
            "lead": {
                "lead_id":           self.lead_id,
                "name":              self.name,
                "email":             self.email,
                "phone":             self.phone,
                "company":           self.company,
                "intent":            self.intent,
                "status":            "escalated",
                "account_type":      self.account_type,
                "account_status":    self.account_status,
                "kyc_status":        self.kyc_status,
                "fraud_hold_active": self.fraud_hold_active,
                "transactions":      self.transactions,
                "account_holds":     self.account_holds,
                "open_refunds":      self.open_refunds,
                "open_disputes":     self.open_disputes,
                "active_fraud_cases": self.active_fraud_cases,
            },
            "workflow_summary":   self.workflow_summary,
            "last_user_message":  self.last_user_message,
            "key_interests":      self.key_interests,
            "sentiment_status":   self.sentiment_status,
            "transcript_excerpt": self.transcript_excerpt,
            "call_duration_sec":  self.call_duration_sec,
            "last_tool_attempted":self.last_tool_attempted,
        }


def _mask_email(email: str) -> str:
    """ar***@company.com"""
    if "@" not in email:
        return email
    local, domain = email.split("@", 1)
    return f"{local[:2]}***@{domain}" if len(local) > 2 else f"***@{domain}"


def _mask_phone(phone: str) -> str:
    """***210"""
    return f"***{phone[-3:]}" if phone and len(phone) >= 3 else phone


def build_escalation_packet(session, reason: str = "customer_request") -> EscalationPacket | None:
    """
    Builds EscalationPacket from session state with completeness guard.
    Auto-fills fields from session.workflow (WorkflowProgress) and session.conv_context.
    Returns None if both intent AND last_user_message are still missing.
    """
    # workflow is a WorkflowProgress (steps_taken, pending_consent_*) — not a WorkflowSummary
    wf = getattr(session, "workflow", None)
    conv_ctx = getattr(session, "conv_context", None)

    # Intent — from conversational context; fallback to reason string
    intent_str = "unknown"
    if conv_ctx is not None:
        ci = getattr(conv_ctx, "conversation_intent", None)
        if ci is not None:
            intent_str = ci.value if hasattr(ci, "value") else str(ci)
    if intent_str in ("unknown", "UNKNOWN"):
        intent_str = reason  # e.g. "fraud_suspected" is more useful than "unknown"

    # Last user message
    last_user_msg = getattr(session, "_last_transcript", "") or ""

    # Workflow summary — serialise steps_taken list into readable text
    if wf is not None and hasattr(wf, "steps_taken") and wf.steps_taken:
        step_parts = [
            f"{s.get('step', '?')}→{s.get('key', '?')}"
            for s in wf.steps_taken[-8:]
        ]
        workflow_summary = "Steps: " + ", ".join(step_parts)
    else:
        workflow_summary = "unknown"

    # Lead info — Fin flow stores everything in customer_profile after verify_account.
    # Wavvy flow stores entities in conv_context.active_entities.
    customer_profile = getattr(session, "customer_profile", {}) or {}
    entities: dict = {}
    if conv_ctx is not None:
        entities = getattr(conv_ctx, "active_entities", {}) or {}

    raw_email = entities.get("email") or customer_profile.get("email", "")
    raw_phone = entities.get("phone") or customer_profile.get("phone", "")

    # Sentiment — derived from session.sentiment_scores (list of 0.0–1.0 floats)
    scores = getattr(session, "sentiment_scores", []) or []
    sentiment: str | None = None
    if scores:
        last_score = scores[-1]
        if last_score >= 0.6:
            sentiment = "positive"
        elif last_score >= 0.35:
            sentiment = "neutral"
        else:
            sentiment = "negative"

    # Duration
    started_at = getattr(session, "started_at", None)
    duration_sec = int((datetime.now(timezone.utc) - started_at).total_seconds()) if started_at else 0

    # Transcript excerpt — last 10 messages from conversation_history + last user utterance
    history = getattr(session, "conversation_history", [])
    excerpt = [
        {"role": t.get("role", "assistant"), "content": t.get("content", "")}
        for t in history[-10:]
        if t.get("content")
    ]
    if last_user_msg:
        excerpt.insert(0, {"role": "user", "content": last_user_msg})

    # Key interests — derive from steps_taken tool names (deduplicated, ordered)
    key_interests: list[str] = []
    if wf is not None and hasattr(wf, "steps_taken"):
        seen: set[str] = set()
        for s in wf.steps_taken:
            step = s.get("step", "")
            if step and step not in seen:
                seen.add(step)
                key_interests.append(step)

    return EscalationPacket(
        call_id=session.call_id,
        lead_id=getattr(session, "lead_id", None),
        name=entities.get("name") or customer_profile.get("name"),
        email=_mask_email(raw_email) if raw_email else None,
        phone=_mask_phone(raw_phone) if raw_phone else None,
        company=entities.get("company"),
        intent=intent_str,
        workflow_summary=workflow_summary,
        last_user_message=last_user_msg,
        key_interests=key_interests,
        sentiment_status=sentiment,
        transcript_excerpt=excerpt,
        call_duration_sec=duration_sec,
        last_tool_attempted=getattr(session, "_last_tool_attempted", None),
        failure_reason=reason,
        account_type=customer_profile.get("account_type"),
        account_status=customer_profile.get("account_status"),
        kyc_status=customer_profile.get("kyc_status"),
        fraud_hold_active=bool(customer_profile.get("fraud_hold_active", False)),
        transactions=customer_profile.get("transactions", []),
        account_holds=customer_profile.get("account_holds", []),
        open_refunds=customer_profile.get("open_refunds", []),
        open_disputes=customer_profile.get("open_disputes", []),
        active_fraud_cases=customer_profile.get("active_fraud_cases", []),
    )
