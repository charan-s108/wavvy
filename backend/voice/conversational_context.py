"""
Per-call conversational context: domain, intent, goal, repair state, topic history.
Three-dimension model — domain / intent / goal are tracked independently.

Injected into every LLM call via to_compact() (~25 tokens).
Updated by _orchestrate() on every turn.
"""
import re
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum


class ConversationalIntent(Enum):
    """
    Fine-grained intent within the CONVERSATIONAL tier.
    Purely observational — never controls routing or orchestration.
    Used for: KB query narrowing, FAST-mode cache fingerprint, analytics,
    response length policy (COMPARISON/TECHNICAL → 40 words).
    Classified by fast regex pass before LLM call (< 5ms, zero API cost).
    """
    GREETING     = "greeting"
    PRICING      = "pricing"
    COMPARISON   = "comparison"
    INTEGRATION  = "integration"
    TECHNICAL    = "technical"
    SECURITY     = "security"
    SMALL_TALK   = "small_talk"
    FOLLOW_UP    = "follow_up"
    UNKNOWN      = "unknown"


# Fast keyword classification for ConversationalIntent
_INTENT_PATTERNS: list[tuple[ConversationalIntent, list[str]]] = [
    (ConversationalIntent.PRICING, [
        r'\bpric\b', r'\bcost\b', r'\bhow much\b', r'\bplan\b',
        r'\btier\b', r'\bsubscription\b', r'\bbudget\b', r'\bfree\b',
        r'\bpaid\b', r'\blicense\b', r'\bafford\b',
    ]),
    (ConversationalIntent.COMPARISON, [
        r'\bvapi\b', r'\bretell\b', r'\bbland\b', r'\belevenlabs\b',
        r'\bvocode\b', r'\btwilio\b', r'\bcompare\b', r'\bvs\b',
        r'\bdifference\b', r'\balternative\b', r'\bbetter than\b',
        r'\bcompetitor\b', r'\bversus\b',
    ]),
    (ConversationalIntent.INTEGRATION, [
        r'\bintegrat\b', r'\bapi\b', r'\bsdk\b', r'\bdeploy\b',
        r'\bself.host\b', r'\bopen.source\b', r'\bgithub\b', r'\bembed\b',
        r'\bsetup\b', r'\binstall\b', r'\bget started\b', r'\bdocumentation\b',
        r'\bdocs\b', r'\bwebhook\b',
    ]),
    (ConversationalIntent.TECHNICAL, [
        r'\btech stack\b', r'\bvoice ai\b', r'\barchitecture\b',
        r'\bpipecat\b', r'\blivekit\b', r'\bdeepgram\b',
        r'\bkokoro\b', r'\bsilero\b', r'\brag\b', r'\bllm\b',
        r'\bwebrtc\b', r'\bstt\b', r'\btts\b', r'\bvad\b',
    ]),
    (ConversationalIntent.SECURITY, [
        r'\bsecur\b', r'\bcomplian\b', r'\bsoc\s*2\b', r'\bgdpr\b',
        r'\bencrypt\b', r'\bprivacy\b', r'\baudit\b', r'\bpii\b',
        r'\bauth\b', r'\b2fa\b',
    ]),
    (ConversationalIntent.GREETING, [
        r'^\s*(?:hi|hello|hey|good\s+(?:morning|afternoon|evening))\s*[!,.]?\s*$',
    ]),
    (ConversationalIntent.FOLLOW_UP, [
        r'\bwhat about\b', r'\band for\b', r'\bhow about\b',
        r'\bwhat if\b', r'\bwhat else\b', r'\bone more\b',
    ]),
    (ConversationalIntent.SMALL_TALK, [
        r'\bhow are you\b', r'\bwhat\'?s up\b', r'\bhow\'?s it going\b',
        r'\bthat\'?s cool\b', r'\binteresting\b',
    ]),
]


def classify_conversational_intent(text: str) -> ConversationalIntent:
    """Fast regex-based intent classification — < 5ms, zero API cost."""
    lower = text.lower()
    for intent, patterns in _INTENT_PATTERNS:
        if any(re.search(p, lower) for p in patterns):
            return intent
    return ConversationalIntent.UNKNOWN


def _kb_cache_fingerprint(
    domain: str | None,
    intent: ConversationalIntent,
    entities: dict[str, str],
) -> str:
    """
    Stable fingerprint for KB result reuse.
    Incorporates domain + intent + key entities so that "Retell pricing"
    and "enterprise pricing" do not share the same cached snippet.
    """
    d = domain or "unknown"
    entity_str = ",".join(f"{k}:{v}" for k, v in sorted(entities.items()) if v)
    return f"{d}|{intent.value}|{entity_str}"


@dataclass
class ConversationalContext:
    """
    Lightweight per-call context for the conversation engine.
    Updated every turn in _orchestrate(). Injected into LLM via to_compact().

    Three independent dimensions:
      conversation_domain  — broad area ("competitor_comparison", "pricing")
      conversation_intent  — specific sub-question (ConversationalIntent enum)
      user_goal            — posture ("exploring", "evaluating", "booking", "frustrated")

    These update independently. A pricing question mid-competitor-comparison keeps
    domain=competitor_comparison while switching intent=PRICING.
    """

    # ── Domain (coarse topic, with decay) ─────────────────────────────────────
    conversation_domain:   str | None           = None
    domain_confidence:     float                = 1.0   # decays 15%/turn without reinforcement
    domain_turn_count:     int                  = 0
    _domain_set_at:        float                = field(default_factory=time.monotonic)
    domain_history:        deque                = field(
        default_factory=lambda: deque(maxlen=3)
    )
    DOMAIN_TTL_S:          float                = 90.0

    # ── Intent (fine-grained) ─────────────────────────────────────────────────
    conversation_intent:   ConversationalIntent = ConversationalIntent.UNKNOWN
    intent_confidence:     float                = 1.0

    # ── Goal and posture ──────────────────────────────────────────────────────
    user_goal:             str | None           = None  # exploring|evaluating|booking|frustrated

    # ── Grounding ─────────────────────────────────────────────────────────────
    last_user_question:    str | None           = None  # verbatim, capped at 100 chars
    last_assistant_action: str | None           = None
    unresolved_questions:  list                 = field(default_factory=list)  # max 3
    active_entities:       dict                 = field(default_factory=dict)

    # ── Repair state ──────────────────────────────────────────────────────────
    repair_pending:        bool                 = False
    repair_target:         str | None           = None
    repair_type:           str | None           = None  # "semantic" | "entity" | "polarity"

    # ── Acknowledgement cooldown (prevents iid-random clustering) ────────────
    last_ack_at:              float             = 0.0
    consecutive_silent_acks:  int               = 0

    # ── KB cache (keyed by semantic fingerprint) ──────────────────────────────
    last_kb_snippet:       str | None           = None
    last_kb_fingerprint:   str | None           = None

    # ── Shift detection phrases ───────────────────────────────────────────────
    _HARD_SHIFT_PHRASES: frozenset = field(default_factory=lambda: frozenset([
        "different question", "change the subject", "change topic",
        "forget that", "never mind that", "completely different",
        "unrelated question", "moving on to", "separate question",
    ]))
    _SOFT_SHIFT_PHRASES: frozenset = field(default_factory=lambda: frozenset([
        "also", "one more thing", "quick question", "by the way",
        "wait", "hold on", "actually", "back to",
    ]))

    def is_domain_fresh(self) -> bool:
        return bool(
            self.conversation_domain
            and self.domain_confidence >= 0.3
            and time.monotonic() - self._domain_set_at < self.DOMAIN_TTL_S
        )

    def check_domain_shift(self, text: str) -> tuple[bool, bool]:
        """Returns (is_hard_shift, is_soft_shift). Both can be False."""
        t = text.lower()
        hard = any(p in t for p in self._HARD_SHIFT_PHRASES)
        soft = not hard and any(p in t for p in self._SOFT_SHIFT_PHRASES)
        return hard, soft

    def set_domain(
        self,
        domain: str,
        intent: ConversationalIntent | None = None,
        goal: str | None = None,
    ) -> None:
        if domain != self.conversation_domain:
            if self.conversation_domain:
                self.domain_history.append(self.conversation_domain)
            self.conversation_domain = domain
            self.domain_confidence = 1.0
            self.domain_turn_count = 0
            self._domain_set_at = time.monotonic()
        else:
            self.domain_turn_count += 1
            self.domain_confidence = min(1.0, self.domain_confidence + 0.05)
        if intent is not None:
            self.conversation_intent = intent
            self.intent_confidence = 1.0
        if goal:
            self.user_goal = goal

    def decay_domain(self) -> None:
        """Call once per turn when domain not reinforced."""
        self.domain_confidence *= 0.85
        if self.domain_confidence < 0.3:
            self.conversation_domain = None
            self.domain_confidence = 1.0
            self.conversation_intent = ConversationalIntent.UNKNOWN

    def mark_last_turn_invalid(self, repair_type: str = "semantic") -> None:
        """
        Repair: mark the last assistant turn wrong, retain domain history.

        Three repair types:
        - "semantic": wrong answer axis (features vs pricing) — local correction, keep domain
        - "entity":   wrong entity referenced ("Retell" vs "Bland") — keep domain, update intent
        - "polarity": user explicitly negated ("I DON'T want a demo") — caller must
          also rewind workflow state (clear pending_action, invalidate collected_entities)

        In all cases: retain domain_history. Domain itself usually stays relevant.
        """
        self.repair_pending = True
        self.repair_target = self.conversation_domain
        self.repair_type = repair_type
        self.domain_confidence *= 0.6   # decay but don't wipe

    def record_question(self, text: str) -> None:
        self.last_user_question = text[:100]

    def get_cached_kb(
        self,
        domain: str | None,
        intent: ConversationalIntent,
        entities: dict[str, str],
    ) -> str | None:
        if not self.is_domain_fresh() or not self.last_kb_snippet:
            return None
        fp = _kb_cache_fingerprint(domain, intent, entities)
        return self.last_kb_snippet if fp == self.last_kb_fingerprint else None

    def store_kb_result(
        self,
        snippet: str,
        domain: str | None,
        intent: ConversationalIntent,
        entities: dict[str, str],
    ) -> None:
        self.last_kb_snippet = snippet
        self.last_kb_fingerprint = _kb_cache_fingerprint(domain, intent, entities)

    def to_compact(self) -> str:
        """~20-35 token string for LLM injection via build_llm_messages()."""
        parts = []
        if self.is_domain_fresh():
            parts.append(f"domain={self.conversation_domain}")
        if self.conversation_intent != ConversationalIntent.UNKNOWN:
            parts.append(f"intent={self.conversation_intent.value}")
        if self.user_goal:
            parts.append(f"goal={self.user_goal}")
        if self.last_assistant_action:
            parts.append(f"prev={self.last_assistant_action}")
        if self.unresolved_questions:
            parts.append(f"open={self.unresolved_questions[0][:25]}")
        if self.repair_pending:
            parts.append(f"repair={self.repair_type or 'true'}")
        return "; ".join(parts) if parts else "start_of_call"


@dataclass
class ConversationMemorySummary:
    """
    Rolling ~20-token rule-based summary of the call so far.
    Rebuilt every 5 turns. Never contains PII. No API call — < 1ms.
    Injected into build_llm_messages() as a "Memory:" system message.
    """
    text:         str = ""
    _turn_seen:   int = 0
    UPDATE_EVERY: int = 5

    def should_update(self, turn_count: int) -> bool:
        return turn_count > 0 and turn_count % self.UPDATE_EVERY == 0

    def to_token_str(self) -> str:
        return self.text[:120] if self.text else ""


def rebuild_memory(session: object, conv: ConversationalContext) -> str:
    """
    Build a compact memory string from session + conv state.
    Rule-based only — no API call, < 1ms.
    """
    parts = []
    if conv.user_goal:
        parts.append(f"user={conv.user_goal}")
    if conv.domain_history:
        parts.append(f"domains={','.join(list(conv.domain_history)[-2:])}")
    # Lead captured check (workflow summary)
    wf = getattr(session, "workflow", None)
    if wf and getattr(getattr(wf, "summary", None), "lead_captured", False):
        parts.append("lead_captured")
    # Frustration signal
    scores = getattr(session, "sentiment_scores", [])
    recent = scores[-4:] if len(scores) >= 4 else []
    if recent and sum(recent) / len(recent) < 0.3:
        parts.append("frustrated")
    if conv.unresolved_questions:
        parts.append(f"open={conv.unresolved_questions[0][:20]}")
    return "; ".join(parts)
