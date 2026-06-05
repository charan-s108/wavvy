"""
Centralized policy decisions for _orchestrate().
Pure functions — no side effects, no I/O. Easy to unit-test and A/B tune.

Every boolean branch in _orchestrate() delegates here instead of accumulating
inline conditionals. This keeps _orchestrate() under 200 lines across all phases.

Phase 1: class created, not yet wired into _orchestrate().
Phase 3: _orchestrate() rewrite delegates all policy decisions here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from voice.conversational_context import (
        ConversationalContext,
        ConversationalIntent,
    )
    from session.call_session import CallSession


class ResponseMode:
    INSTANT  = "instant"   # < 50ms  — deterministic fast response (RECOVERY/TRANSACTIONAL)
    FAST     = "fast"      # < 400ms — LLM, no KB search (domain fresh + cache hit)
    STANDARD = "standard"  # < 800ms — LLM + KB search (default)


class RoutingTier:
    TRANSACTIONAL  = "transactional"
    CONVERSATIONAL = "conversational"
    RECOVERY       = "recovery"


@dataclass
class ConversationPolicy:
    """
    All routing + quality policy decisions in one place.
    Construct once per call (or once globally — all methods are pure).
    Add `policy: ConversationPolicy = field(default_factory=ConversationPolicy)`
    to CallSession.
    """

    def should_call_llm(
        self,
        tier: str,
        directive_type: str | None,
        kb_snippet_available: bool,
        kb_collection_empty: bool,
    ) -> bool:
        """
        False for RECOVERY (deterministic response), ACKNOWLEDGEMENT (no LLM needed),
        and zero-KB empty-collection cases (serve canned response to avoid hallucination).
        """
        if tier == RoutingTier.RECOVERY:
            return False
        if directive_type == "acknowledgement":
            return False
        if not kb_snippet_available and kb_collection_empty:
            return False
        return True

    def should_acknowledge(
        self,
        directive_type: str | None,
        directive_confidence: float,
    ) -> bool:
        """True when utterance is a pure acknowledgement needing no LLM or KB."""
        return directive_type == "acknowledgement" and directive_confidence >= 0.75

    def should_escalate(self, session: "CallSession") -> bool:
        """Three-score escalation gate."""
        scores = getattr(session, "escalation_scores", None)
        if scores is None:
            return False
        # Explicit handoff request
        if getattr(scores, "explicit_handoff", False):
            return True
        # Technical failures
        if getattr(scores, "technical_failures", 0) >= 3:
            return True
        # Sustained frustration: 4 of last 5 scores below 0.3, on a mature call.
        # Requires turn_count >= 20 — early fragments and short tech questions can
        # score below 0.3 without reflecting genuine frustration (false signal region).
        recent = list(session.sentiment_scores[-5:])
        turn_count = getattr(session, "turn_count", 0)
        if (len(recent) >= 5
                and sum(1 for s in recent if s < 0.3) >= 4
                and turn_count >= 20):
            return True
        # Comprehension failures on a mature call
        comp = getattr(scores, "comprehension_failures", 0)
        turn_count = getattr(session, "turn_count", 0)
        import time
        duration = time.monotonic() - getattr(session, "_started_monotonic", time.monotonic())
        if comp >= 12 and turn_count >= 8 and duration >= 60:
            return True
        return False

    def should_skip_kb(
        self,
        tier: str,
        conv: "ConversationalContext",
        mode: str,
    ) -> bool:
        """Skip KB search when tier is deterministic, or FAST mode has a cache hit."""
        if tier in (RoutingTier.RECOVERY, RoutingTier.TRANSACTIONAL):
            return True
        if mode == ResponseMode.FAST and conv.last_kb_snippet:
            return True
        return False

    def response_mode(
        self,
        tier: str,
        conv: "ConversationalContext",
        kb_cache_fresh: bool,
    ) -> str:
        """Select INSTANT / FAST / STANDARD based on tier and context freshness."""
        if tier in (RoutingTier.RECOVERY, RoutingTier.TRANSACTIONAL):
            return ResponseMode.INSTANT
        if conv.is_domain_fresh() and kb_cache_fresh:
            return ResponseMode.FAST
        return ResponseMode.STANDARD

    def max_response_words(self, intent: str) -> int:
        """
        Dynamic word budget — prevents 25-word hard limit from hurting complex answers.
        Simple answers: 25 words. Comparisons / technical explanations: 40 words.
        """
        if intent in ("comparison", "technical", "integration", "security"):
            return 40
        return 25

    def silence_reset_strength(self, tier: str, directive_type: str | None) -> str:
        """
        Weighted silence reset — prevents filler/acks from restarting full 40-second lifecycle.
        FULL: transactional / substantive conversational answer
        PARTIAL: acknowledgement (reduce elapsed by 50%)
        NONE: RECOVERY-tier filler (no reset)
        """
        if tier == RoutingTier.RECOVERY:
            return "none"
        if directive_type == "acknowledgement":
            return "partial"
        return "full"
