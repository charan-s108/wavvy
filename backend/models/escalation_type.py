"""
EscalationType — classifies why an escalation happened.
Used to shape the Case Intelligence output and Handoff Card presentation.
"""
from __future__ import annotations

from enum import Enum


class EscalationType(str, Enum):
    AUTHORITY  = "authority"   # AI knew the answer, lacked permission to act
    EMOTION    = "emotion"     # sentiment collapse or explicit human request
    AMBIGUITY  = "ambiguity"   # conflicting evidence; AI couldn't determine ground truth
    NOVELTY    = "novelty"     # no workflow covers this case


def classify_escalation_type(session) -> EscalationType:
    """
    Classify the escalation from session state.
    Priority: explicit_handoff > technical_failures > comprehension_failures > sentiment > default.
    """
    esc_scores = getattr(session, "escalation_scores", None)
    failure_reason = getattr(session, "escalation_reason", None) or ""

    # Explicit customer request or sentiment collapse → EMOTION
    if failure_reason in ("customer_request", "sentiment"):
        return EscalationType.EMOTION
    if esc_scores and esc_scores.explicit_handoff:
        return EscalationType.EMOTION

    # Tool/technical failure → AI had the answer, execution failed → AUTHORITY
    if failure_reason == "tool_failure":
        return EscalationType.AUTHORITY
    if esc_scores and esc_scores.technical_failures > 0:
        return EscalationType.AUTHORITY

    # Repeated comprehension failures → AMBIGUITY (AI couldn't parse the situation)
    if esc_scores and esc_scores.comprehension_failures >= 2:
        return EscalationType.AMBIGUITY

    # Sentiment scores trending bad (last 2 below 0.3) → EMOTION
    scores = getattr(session, "sentiment_scores", []) or []
    if len(scores) >= 2 and scores[-1] < 0.3 and scores[-2] < 0.3:
        return EscalationType.EMOTION

    # Unknown threshold — not enough context → NOVELTY
    if failure_reason in ("unknown_threshold", ""):
        return EscalationType.NOVELTY

    return EscalationType.NOVELTY
