"""
Layer 1, Step 3: Local intent classification + entity extraction.
Target: <10ms. Zero API calls. Keyword matching with confidence scoring.

Intent Router is initialization-only. Once a workflow is active, the Workflow Engine
drives step transitions — the Intent Router is NOT consulted again.

Phase 2.5 — Shadow routing: classify_tier() runs alongside classify_intent() for
divergence logging. Phase 3 will replace classify_intent() with classify_tier().
"""
import re
import logging
from enum import Enum
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ── Three-Tier Routing (Phase 2.5 shadow; Phase 3 primary) ───────────────────

class RoutingTier(Enum):
    TRANSACTIONAL  = "transactional"   # < 10ms, 0 LLM calls, deterministic
    CONVERSATIONAL = "conversational"  # ≤ 500ms, 1 LLM call
    RECOVERY       = "recovery"        # < 50ms, 0 LLM calls, filler/noise


class TransactionalIntent(Enum):
    DEMO_REQUEST = "demo_request"
    HUMAN_AGENT  = "human_agent"


_GREETING_UTTERANCES = frozenset({
    "hi", "hello", "hey",
    "good morning", "good afternoon", "good evening",
    "hi there", "hey there",
})

_RECOVERY_UTTERANCES = frozenset({
    "uh", "um", "umm", "hmm", "ah", "err", "oh",
    "yeah", "yep", "okay", "ok", "right", "sure", "mhm",
    "hello?", "are you there", "can you hear me", "hello hello",
})


def _match_demo_request(text: str) -> float:
    patterns = _INTENT_PATTERNS[Intent.DEMO_REQUEST]
    lower = text.lower()
    matches = sum(1 for p in patterns if re.search(p, lower))
    if matches == 0:
        return 0.0
    return min(0.4 + (matches * 0.2), 0.95)


def _match_human_agent(text: str) -> float:
    patterns = _INTENT_PATTERNS[Intent.HUMAN_AGENT]
    lower = text.lower()
    matches = sum(1 for p in patterns if re.search(p, lower))
    if matches == 0:
        return 0.0
    return min(0.4 + (matches * 0.2), 0.95)


def is_recovery_utterance(clean: str, stt_confidence: float) -> bool:
    """
    True for filler speech, channel checks, or very low-confidence audio.
    Greetings are NOT recovery — they're conversational openers.
    """
    if clean in _RECOVERY_UTTERANCES:
        return True
    if stt_confidence < 0.4 and len(clean.split()) <= 3:
        return True
    return False


def classify_tier(
    text: str,
    stt_confidence: float = 1.0,
) -> tuple[RoutingTier, TransactionalIntent | None]:
    """
    Three-tier classifier. Phase 2.5: run in shadow alongside classify_intent().
    Phase 3: this becomes the primary routing function.

    Returns (RoutingTier, TransactionalIntent | None).
    TransactionalIntent is only set for TRANSACTIONAL tier.
    """
    lower = text.lower().strip()
    clean = lower.strip("?!., ")

    # Recovery first — must use unstripped `lower` so "hello?" matches _RECOVERY_UTTERANCES
    # rather than stripping to "hello" and incorrectly routing as a greeting.
    if is_recovery_utterance(lower, stt_confidence):
        return RoutingTier.RECOVERY, None

    # Greetings → CONVERSATIONAL (stripped form — "hello" not "hello?")
    if clean in _GREETING_UTTERANCES:
        return RoutingTier.CONVERSATIONAL, None

    # Transactional: high-confidence structured command + high STT confidence
    if _match_demo_request(text) >= INTENT_CONFIDENCE_THRESHOLD and stt_confidence >= 0.7:
        return RoutingTier.TRANSACTIONAL, TransactionalIntent.DEMO_REQUEST
    if _match_human_agent(text) >= INTENT_CONFIDENCE_THRESHOLD and stt_confidence >= 0.7:
        return RoutingTier.TRANSACTIONAL, TransactionalIntent.HUMAN_AGENT

    return RoutingTier.CONVERSATIONAL, None


def _tier_to_legacy_intent(tier: RoutingTier, ti: TransactionalIntent | None) -> str:
    """Map new tier to legacy Intent value for shadow divergence comparison."""
    if tier == RoutingTier.TRANSACTIONAL:
        if ti == TransactionalIntent.DEMO_REQUEST:
            return Intent.DEMO_REQUEST.value
        return Intent.HUMAN_AGENT.value
    if tier == RoutingTier.RECOVERY:
        return Intent.UNKNOWN.value
    return "conversational"  # CONVERSATIONAL maps to no single legacy intent

INTENT_CONFIDENCE_THRESHOLD = 0.7
UNKNOWN_ESCALATE_THRESHOLD = 3       # escalate after N consecutive UNKNOWNs
UNKNOWN_ESCALATE_NEG_THRESHOLD = 2   # escalate after N UNKNOWNs + negative sentiment


class Intent(Enum):
    PRODUCT_QA         = "product_qa"         # "What is Wavvy?", "How does it work?"
    PRICING_INQUIRY    = "pricing_inquiry"     # "How much?", "What plans?"
    DEMO_REQUEST       = "demo_request"        # "Schedule a demo", "Book a call"
    COMPETITOR_COMPARE = "competitor_compare"  # "vs Vapi", "vs Retell", "compare"
    INTEGRATION_QA     = "integration_qa"     # "How do I integrate?", "What APIs?"
    HUMAN_AGENT        = "human_agent"         # "Talk to someone", "Connect me"
    GENERAL_QA         = "general_qa"          # catch-all Wavvy Q&A
    UNKNOWN            = "unknown"


# ── Keyword patterns per intent ───────────────────────────────────────────────

_INTENT_PATTERNS: dict[Intent, list[str]] = {
    Intent.PRODUCT_QA: [
        r'\bwhat is wavvy\b', r'\bhow does wavvy work\b', r'\bwhat does wavvy do\b',
        r'\bfeatures\b', r'\bcapabilities\b', r'\btell me about wavvy\b',
        r'\btech stack\b', r'\bvoice ai\b', r'\bwhat can wavvy\b',
        r'\bhow it works\b', r'\bwhat wavvy\b', r'\babout wavvy\b',
    ],
    Intent.PRICING_INQUIRY: [
        r'\bpric\b', r'\bcost\b', r'\bhow much\b', r'\bplan\b',
        r'\btier\b', r'\bsubscription\b', r'\bbudget\b', r'\bafford\b',
        r'\bfree\b', r'\bpaid\b', r'\blicense\b',
    ],
    Intent.DEMO_REQUEST: [
        r'\bdemo\b', r'\bschedule\b', r'\bbook\b', r'\btrial\b',
        r'\bsee it in action\b', r'\bappointment\b', r'\btest it\b',
        r'\bshow me\b.*\bwavvy\b', r'\bwant to try\b',
        # Compound phrases — each independently signals demo intent so common
        # single-keyword utterances ("Can we have a demo?") accumulate ≥2 matches
        # and cross the 0.7 routing threshold without lowering it globally.
        r'\bhave a demo\b',           # "Can we have a demo?"
        r'\bget a demo\b',            # "I want to get a demo"
        r'\bsee a demo\b',            # "Can I see a demo?"
        r'\bbook a demo\b',           # "Can I book a demo?"
        r'\bset.{0,8}demo\b',         # "Set a demo", "Set up a demo"
        r'\bshow me\b.{0,20}demo\b',  # "Show me a demo how it works"
        r'\bwould like\b.{0,20}demo\b',  # "I would like to have a demo"
        r'\binterested in\b.{0,20}demo\b',  # "I'm interested in a demo"
        r'\bsign(?:ing)?\s+up\b.{0,15}demo\b',  # "signing up for a demo"
        r'\brequest(?:ing)?\b.{0,10}demo\b',     # "requesting a demo"
    ],
    Intent.COMPETITOR_COMPARE: [
        r'\bvapi\b', r'\bretell\b', r'\bbland\b', r'\belevenlabs\b',
        r'\bvocode\b', r'\btwilio\b', r'\bcompare\b', r'\bvs\b',
        r'\bdifference\b', r'\balternative\b', r'\bbetter than\b',
        r'\bcompetitor\b', r'\bversus\b',
    ],
    Intent.INTEGRATION_QA: [
        r'\bintegrat\b', r'\bapi\b', r'\bsdk\b', r'\bdeploy\b',
        r'\bself.host\b', r'\bopen.source\b', r'\bgithub\b', r'\bembed\b',
        r'\bsetup\b', r'\binstall\b', r'\bget started\b', r'\bhow to use\b',
        r'\bdocumentation\b', r'\bdocs\b', r'\bwebhook\b',
    ],
    Intent.HUMAN_AGENT: [
        r'\bhuman\b', r'\bagent\b', r'\bperson\b', r'\bsomeone\b',
        r'\bwavvy team\b', r'\btalk to\b', r'\bspeak with\b', r'\bspeak to\b',
        r'\bconnect me\b', r'\bsales\b', r'\bsupport\b', r'\bescalate\b',
        r'\btransfer\b',
    ],
}

# ── Entity extraction ─────────────────────────────────────────────────────────

# Words that can NEVER be part of a person's name.
# Gerunds, adjectives, adverbs, and common small-talk completions after "I'm".
_NAME_STOP_WORDS = frozenset([
    # Present participles / gerunds ("I'm doing ...", "I'm calling ...")
    "doing", "feeling", "thinking", "wondering", "hoping", "looking",
    "calling", "trying", "asking", "going", "coming", "helping", "working",
    "considering", "planning", "reaching", "checking", "following",
    # Adjectives / adverbs common after "I'm" or "I am"
    "well", "good", "fine", "okay", "ok", "great", "awesome", "terrible",
    "tired", "excited", "ready", "sure", "happy", "sad", "busy", "new",
    "interested", "curious", "confused", "afraid", "sorry", "worried",
    "nervous", "just", "here", "back", "not", "better", "much",
])

# Exact multi-word phrases that are never names — checked after title-casing.
_INVALID_NAME_PHRASES = frozenset([
    "doing well", "not sure", "not bad", "pretty good", "feeling good",
    "doing great", "doing fine", "okay thanks", "all good", "all right",
    "quite well", "very well", "feeling well",
])


def is_valid_person_name(value: str) -> bool:
    """
    Returns True only if value is a plausible person name.

    Rejects: gerunds, adjectives, emotional states, multi-word status phrases,
    and anything > 3 words. Designed to block "I'm doing well" → "Doing Well".
    """
    if not value:
        return False
    cleaned = value.strip().lower()
    if not cleaned:
        return False
    if cleaned in _INVALID_NAME_PHRASES:
        return False
    words = cleaned.split()
    if len(words) == 0 or len(words) > 3:
        return False
    # Any stop word in any position → not a name
    if any(w in _NAME_STOP_WORDS for w in words):
        return False
    return True


# Name patterns — common name indicators.
# Order matters: most specific first. All allow lower-case names (STT rarely capitalizes).
_NAME_PATTERNS = [
    r'\bmy\s+name(?:\'?s|\s+is)\s+([A-Za-z][A-Za-z\s]{1,30})',   # "my name is jerry"
    r'\bit\'?s\s+me[,\s]+([A-Za-z][A-Za-z]{1,20})',               # "it's me, jerry"
    r'\bthis\s+is\s+([A-Za-z][A-Za-z\s]{1,20})',                   # "this is jerry"
    r'\bi\'?m\s+([A-Za-z][a-z]+(?:\s+[A-Za-z][a-z]+)?)',          # "i'm jerry"
    r'\bcall\s+me\s+([A-Za-z][A-Za-z\s]{1,20})',                   # "call me jerry"
]

# Intro phrases stripped from the raw fallback transcript when entity extraction fails
_NAME_INTRO_RE = re.compile(
    r'^(?:hi[,.\s]+)?(?:'
    r'my\s+name(?:\'?s|\s+is)\s*|'
    r'it\'?s\s+me[,\s]*|'
    r'this\s+is\s+|'
    r'i\'?m\s+|'
    r'call\s+me\s+'
    r')',
    re.IGNORECASE,
)

# Email pattern
_EMAIL_PATTERN = r'\b([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})\b'


def _spoken_to_email(text: str) -> str:
    """
    Normalize voice-spoken email to standard form.
    "tom at gmail dot com"       → "tom@gmail.com"
    "tom at the rate gmail dot com" → "tom@gmail.com"
    """
    t = text.lower()
    t = re.sub(r'\bat\s+the\s+rate\b', '@', t)
    if '@' not in t:
        # "word at word" — only replace the first standalone "at" that looks like email
        t = re.sub(r'\b([\w.+\-]+)\s+at\s+([\w])', r'\1@\2', t, count=1)
    t = re.sub(r'\s+dot\s+', '.', t)   # "dot" → "."
    t = re.sub(r'\s*@\s*', '@', t)     # strip spaces around @
    return t

# Phone — international and local formats
_PHONE_PATTERNS = [
    r'\+?(\d[\d\s\-\.]{8,14}\d)',
]

# Company indicators
_COMPANY_PATTERNS = [
    r'\bfrom\s+([A-Z][a-zA-Z\s&]{2,30}(?:Inc|LLC|Ltd|Corp|Co|Technologies|Tech|Solutions)?)\b',
    r'\bwork(?:ing)?\s+(?:at|for)\s+([A-Z][a-zA-Z\s&]{2,30})\b',
    r'\bcompany\s+(?:is\s+)?([A-Z][a-zA-Z\s&]{2,30})\b',
]

# Preferred time patterns — ordered most-specific to least-specific.
# Each pattern captures the FULL temporal phrase (not just the anchor day).
# Bug fix: "tuesday at 3pm" previously matched only "tuesday"; now captures "tuesday at 3pm".
_TIME_PATTERNS = [
    # "next tuesday at 3pm", "friday at 2:30pm", "tomorrow at 10am"
    r'\b((?:next\s+)?(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|tomorrow)'
    r'\s+at\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\b',
    # "tuesday morning", "next friday afternoon"
    r'\b((?:next\s+)?(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|tomorrow)'
    r'\s+(?:morning|afternoon|evening))\b',
    # Specific date + optional time: "May 27th at 10am", "May 27th"
    r'\b((?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?'
    r'|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)'
    r'\s+\d{1,2}(?:st|nd|rd|th)?(?:\s+at\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?)?)\b',
    # "27th May" ordinal-first form
    r'\b(\d{1,2}(?:st|nd|rd|th)?\s+(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?'
    r'|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?'
    r'|dec(?:ember)?)(?:\s+at\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?)?)\b',
    # "in 2 days", "in a week"
    r'\b(in\s+(?:a\s+)?(?:\d+|one|two|three|four|five|six|seven)\s+(?:days?|weeks?))\b',
    # "next monday", "next week"
    r'\b(next\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|week|month))\b',
    # "this friday", "this week"
    r'\b(this\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|week))\b',
    # Plain day: "tuesday", "tomorrow"
    r'\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday|tomorrow|today)\b',
    # Time only: "3pm", "14:30am"
    r'\b(\d{1,2}(?::\d{2})?\s*(?:am|pm))\b',
    # Period only: "morning", "afternoon", "evening"
    r'\b(morning|afternoon|evening)\b',
    # Generic: "anytime", "flexible"
    r'\b(anytime|any\s+time|flexible|whenever)\b',
]

# Plan type extraction for pricing
_PLAN_PATTERNS = {
    "starter":    [r'\bstarter\b', r'\bsmall\b', r'\bbasic\b'],
    "growth":     [r'\bgrowth\b', r'\bprofessional\b', r'\bpro\b', r'\bmid\b'],
    "enterprise": [r'\benterprise\b', r'\blarge\b', r'\bcustom\b', r'\bbig\b'],
}


def _extract_name(text: str) -> str | None:
    for pattern in _NAME_PATTERNS:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            raw = m.group(1).strip()
            # Take only the first 1–2 words (the name), discard trailing context
            parts = raw.split()[:2]
            candidate = " ".join(p.title() for p in parts)
            if is_valid_person_name(candidate):
                return candidate
    return None


def _extract_email(text: str) -> str | None:
    m = re.search(_EMAIL_PATTERN, text)
    if m:
        return m.group(1).strip().lower()
    # Try normalizing spoken form ("tom at gmail dot com")
    normalized = _spoken_to_email(text)
    m = re.search(_EMAIL_PATTERN, normalized)
    return m.group(1).strip().lower() if m else None


def _extract_phone(text: str) -> str | None:
    for pattern in _PHONE_PATTERNS:
        m = re.search(pattern, text)
        if m:
            digits = re.sub(r'\D', '', m.group(1))
            if len(digits) >= 10:
                return digits
    return None


def _extract_company(text: str) -> str | None:
    for pattern in _COMPANY_PATTERNS:
        m = re.search(pattern, text)
        if m:
            return m.group(1).strip()
    return None


# Time-only input (no day anchor) — used for entity merging during scheduling clarification
_TIME_ONLY_RE = re.compile(
    r'^\s*(?:\d{1,2}(?::\d{2})?\s*(?:am|pm)|morning|afternoon|evening|noon)\s*$',
    re.IGNORECASE,
)
_HAS_DAY_RE = re.compile(
    r'\b(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|tomorrow|today)\b',
    re.IGNORECASE,
)


def _extract_preferred_time(text: str) -> str | None:
    """
    Extract the full temporal expression from text.
    Tries patterns from most-specific to least-specific.
    After finding an anchor (day/date/relative), scans ahead up to 30 chars
    for a clock time or period word to capture the full phrase.

    Examples:
      "tuesday at 3pm"          → "tuesday at 3pm"
      "next friday afternoon"   → "next friday afternoon"
      "May 27th"                → "May 27th"
      "uh maybe next Friday around 4pm" → "next Friday at 4pm"
      "yes that works"          → None
    """
    t = text.lower().strip()

    # Try full-phrase patterns first (most specific)
    for pattern in _TIME_PATTERNS:
        m = re.search(pattern, t, re.IGNORECASE)
        if m:
            matched = m.group(1).strip()
            end_pos = m.end()

            # If the match is just a plain day/relative word, try to pick up
            # a time or period word that follows within the next 30 characters.
            _plain_day = re.compile(
                r'^(?:monday|tuesday|wednesday|thursday|friday|'
                r'saturday|sunday|tomorrow|today|next\s+\w+|this\s+\w+)$',
                re.IGNORECASE,
            )
            if _plain_day.match(matched):
                trailing = t[end_pos:end_pos + 35]
                # Look for clock time after connectors ("at", "around", "@")
                time_m = re.search(
                    r'(?:at\s+|around\s+|about\s+|@\s*)?(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)',
                    trailing, re.IGNORECASE,
                )
                period_m = re.search(
                    r'\b(morning|afternoon|evening|noon|lunchtime)\b',
                    trailing, re.IGNORECASE,
                )
                if time_m and time_m.group(1).strip():
                    matched = f"{matched} at {time_m.group(1).strip()}"
                elif period_m:
                    matched = f"{matched} {period_m.group(1).strip()}"

            return matched

    return None


def _extract_plan_type(text: str) -> str | None:
    lower = text.lower()
    for plan_name, patterns in _PLAN_PATTERNS.items():
        if any(re.search(p, lower) for p in patterns):
            return plan_name
    return None


_DAY_ONLY_RE = re.compile(
    r'\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday|'
    r'today|tomorrow|'
    r'this\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)|'
    r'next\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday))\b',
    re.IGNORECASE,
)

_TIME_COMPONENT_RE = re.compile(
    r'\b(\d{1,2}(?::\d{2})?\s*(?:am|pm)'
    r'|morning|afternoon|evening|noon|lunchtime'
    r"|midnight|o'?clock)\b",
    re.IGNORECASE,
)


def _extract_preferred_day(text: str) -> str | None:
    """Extract just the day name / relative date from text ('thursday', 'next friday')."""
    m = _DAY_ONLY_RE.search(text)
    return m.group(1).strip().lower() if m else None


def _extract_time_only(text: str) -> str | None:
    """Extract only the clock-time or period of day ('3pm', 'afternoon') — no day names."""
    m = _TIME_COMPONENT_RE.search(text)
    return m.group(1).strip().lower() if m else None


_entity_logger = logging.getLogger(__name__ + ".entities")


def extract_entities(text: str) -> dict:
    """
    Extract structured entities from normalized transcript.
    Returns dict with any of: name, email, phone, company,
    preferred_day, preferred_time, plan_type.

    preferred_day and preferred_time are collected separately so the demo-booking
    workflow can ask for each in sequence before calling the scheduling tool.
    """
    entities: dict = {}

    name = _extract_name(text)
    if name:
        entities["name"] = name

    email = _extract_email(text)
    if email:
        entities["email"] = email

    phone = _extract_phone(text)
    if phone:
        entities["phone"] = phone

    company = _extract_company(text)
    if company:
        entities["company"] = company

    preferred_day = _extract_preferred_day(text)
    if preferred_day:
        entities["preferred_day"] = preferred_day

    time_only = _extract_time_only(text)
    if time_only:
        entities["preferred_time"] = time_only

    plan_type = _extract_plan_type(text)
    if plan_type:
        entities["plan_type"] = plan_type

    _entity_logger.debug("extract_entities: input=%r → %r", text[:80], entities)
    return entities


# ── Intent classification ─────────────────────────────────────────────────────

def _intent_confidence(text: str, patterns: list[str]) -> float:
    lower = text.lower()
    matches = sum(1 for p in patterns if re.search(p, lower))
    if matches == 0:
        return 0.0
    return min(0.4 + (matches * 0.2), 0.95)


def classify_intent(text: str) -> tuple[Intent, float]:
    """
    Returns (Intent, confidence_score).
    - confidence >= INTENT_CONFIDENCE_THRESHOLD → return that intent
    - confidence < INTENT_CONFIDENCE_THRESHOLD → return (GENERAL_QA, score)
    - confidence < 0.4 + no partial match → return (UNKNOWN, score)

    UNKNOWN handling: Workflow Engine checks _consecutive_unknown_intents.
    Escalation threshold logic belongs to Workflow Engine, NOT here.
    """
    scores: dict[Intent, float] = {}
    for intent, patterns in _INTENT_PATTERNS.items():
        score = _intent_confidence(text, patterns)
        if score > 0:
            scores[intent] = score

    if not scores:
        return Intent.UNKNOWN, 0.0

    best_intent = max(scores, key=lambda i: scores[i])
    best_score = scores[best_intent]

    if best_score >= INTENT_CONFIDENCE_THRESHOLD:
        return best_intent, best_score

    if best_score >= 0.4:
        return Intent.GENERAL_QA, best_score

    return Intent.UNKNOWN, best_score
