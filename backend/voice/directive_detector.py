"""
Layer 1, Step 2: Conversational directive detection.
Runs BEFORE intent router. When workflow is active and a directive resolves,
the intent router is skipped — the Workflow Engine handles the directive directly.
"""
from dataclasses import dataclass
from enum import Enum
import re
import logging

logger = logging.getLogger(__name__)

DIRECTIVE_CONFIDENCE_THRESHOLD = 0.75


class ConversationalDirective(Enum):
    CONFIRM          = "confirm"          # "yes", "go ahead", "do it"
    CANCEL_PENDING   = "cancel_pending"   # "no", "wait", "never mind", "stop"
    REPEAT           = "repeat"           # "what?", "say that again", "pardon"
    CLARIFY          = "clarify"          # "what do you mean", "I don't understand"
    INTERRUPT        = "interrupt"        # barge-in (VAD handles audio; this handles text)
    CORRECT          = "correct"          # "no I said", "I meant", "actually it's"
    ESCALATE         = "escalate"         # "human", "agent", "manager", "talk to someone"
    REPAIR           = "repair"           # "no I meant X", "that's not what I asked"
    ACKNOWLEDGEMENT  = "acknowledgement"  # "got it", "makes sense", "okay cool"
    NONE             = "none"


@dataclass
class DirectiveResult:
    directive: ConversationalDirective
    confidence: float


# Pattern sets — order matters; first match wins for overlapping patterns
_CONFIRM_PATTERNS = [
    r'\byes\b', r'\byep\b', r'\bgo ahead\b', r'\bdo it\b', r'\bconfirm\b',
    r'\bthat\'s right\b', r'\bcorrect\b', r'\bright\b', r'\bsure\b',
    r'\bplease do\b', r'\bproceed\b', r'\bokay\b', r'\bok\b',
]
_CANCEL_PATTERNS = [
    r'\bno\b', r'\bnope\b', r'\bnever mind\b', r'\bnevermind\b',
    r'\bcancel that\b', r'\bforget it\b', r'\bstop\b', r'\bwait\b',
    r'\bdon\'t\b', r'\bdont\b', r'\bhold on\b', r'\bnot now\b',
    r'\bactually no\b',
]
_REPEAT_PATTERNS = [
    r'\bwhat\?\b', r'\bpardon\b', r'\bsay that again\b', r'\brepeat\b',
    r'\bwhat did you say\b', r'\bcan you repeat\b', r'\bsay again\b',
]
_CLARIFY_PATTERNS = [
    r'\bwhat do you mean\b', r'\bi don\'t understand\b', r'\bconfused\b',
    r'\bwhat are you talking about\b', r'\bhuh\b', r'\bi\'m not sure what\b',
    r'\bexplain that\b',
    # r'\bwhat\b' removed — matches every question ("what is wavvy" → false CLARIFY)
]
_CORRECT_PATTERNS = [
    r'\bno i said\b', r'\bi meant\b', r'\bactually it\'s\b', r'\bactually\b',
    r'\bi mean\b', r'\bno not\b', r'\bI said\b',
]
_ESCALATE_PATTERNS = [
    r'\bhuman\b', r'\bagent\b', r'\bmanager\b', r'\badmin\b',
    r'\breal person\b', r'\btalk to\b', r'\bspeak to\b',
    r'\bconnect me\b', r'\bconnect me with\b',
    r'\btransfer\b', r'\brepresentative\b', r'\bcustomer support\b',
    r'\boperator\b', r'\bsomeone else\b', r'\banother person\b',
    r'\blet me talk\b', r'\bi want a human\b', r'\bi need a human\b',
    r'\bget me a person\b', r'\bget me a human\b', r'\bget me someone\b',
    r'\bput me through\b',
    r'\bwith someone\b', r'\bwith a person\b',
]

# REPAIR — user correcting a misunderstood or wrong previous response.
# Detected BEFORE ESCALATE so "no I meant support pricing" doesn't become ESCALATE.
# Pattern: explicit correction marker followed by clarification content.
_REPAIR_PATTERNS = [
    r'\bno[,\s]+(?:i\s+meant|that\'?s\s+not|i\s+said)\b',
    r'\bactually[,\s]+(?:i\s+meant|i\s+wanted|i\s+was\s+asking)\b',
    r'\bwait[,\s]+(?:i\s+meant|that\'?s\s+wrong|no)\b',
    r'\bthat(?:\'s|\s+is)\s+not\s+what\s+i\s+(?:said|meant|asked)\b',
    r'\bsorry[,\s]+i\s+meant\b',
    r'\bno[,\s]+not\s+that\b',
    r'\bi\s+(?:don\'?t|didn\'?t)\s+(?:want|mean|say)\s+(?:a\s+)?demo\b',
]

# REPAIR uses a lower threshold — patterns are long and precise; one match is strong evidence.
_REPAIR_CONFIDENCE_THRESHOLD = 0.65

# CANCEL — bare single/two-word cancellation utterances.
# After normalization "no stop" → "no" (denial map), so "no" alone must cancel at threshold.
# Pattern-based CANCEL handles multi-word phrases ("no cancel that", "never mind").
_CANCEL_UTTERANCES = frozenset([
    "no", "nope", "nah", "stop", "cancel", "abort",
    "never mind", "nevermind", "forget it", "hold on",
])

# CONFIRM — bare single/two-word utterances that are unambiguous confirmations.
# Checked as whole-utterance exact matches (after normalization) at high confidence.
# Pattern-based CONFIRM catches longer phrases ("yes please go ahead", "go ahead").
_CONFIRM_UTTERANCES = frozenset([
    "yes", "yep", "yup", "yeah", "sure", "go ahead",
    "do it", "confirm", "proceed", "please do", "that's right",
])

# ACKNOWLEDGEMENT — conversational continuers that require no LLM or KB response.
# Must be whole-utterance matches (not substring) — check via exact normalized match.
_ACKNOWLEDGEMENT_UTTERANCES = frozenset([
    "got it", "makes sense", "okay cool", "nice", "great",
    "sounds good", "understood", "perfect", "awesome",
    "i see", "fair enough", "that makes sense", "okay", "ok",
    "cool", "alright", "good to know", "noted",
    # Positive feedback phrases commonly said after a satisfying answer
    "good to hear that", "good to hear", "glad to hear that", "glad to hear",
    "happy to hear that", "nice to know", "that's helpful", "that helps",
    "that's good", "that's great", "that's interesting", "interesting",
    "that makes sense", "that's clear", "that's useful", "very helpful",
    "helpful", "thanks", "thank you", "thanks for that",
])


def _match_confidence(text: str, patterns: list[str]) -> float:
    lower = text.lower()
    matches = sum(1 for p in patterns if re.search(p, lower))
    if matches == 0:
        return 0.0
    # More matches = higher confidence, capped at 0.95
    return min(0.5 + (matches * 0.2), 0.95)


def detect_directive(text: str) -> DirectiveResult:
    """
    Returns DirectiveResult{directive, confidence}.

    Priority order (first match at threshold wins):
      1. ESCALATE  — always, regardless of workflow state
      2. REPAIR    — explicit correction before CORRECT/CANCEL to avoid misclassification
      3. ACKNOWLEDGEMENT — whole-utterance continuers (no LLM/KB needed)
      4. CORRECT   — "no I said X"
      5. CANCEL_PENDING / CONFIRM  — yes/no workflow responses
      6. REPEAT / CLARIFY

    Voice edge cases:
    - "yeah no" → CANCEL_PENDING (denial overrides affirmative)
    - "stop stop wait" → CANCEL_PENDING
    - "yeah sure I guess" → low confidence CONFIRM
    - "got it" → ACKNOWLEDGEMENT (no LLM, no KB, optional brief verbal ack)
    """
    if not text or not text.strip():
        return DirectiveResult(ConversationalDirective.NONE, 0.0)

    lower = text.lower().strip()

    # ESCALATE is always detected — never blocked by workflow state
    esc = _match_confidence(lower, _ESCALATE_PATTERNS)
    if esc >= DIRECTIVE_CONFIDENCE_THRESHOLD:
        return DirectiveResult(ConversationalDirective.ESCALATE, esc)

    # REPAIR — explicit correction; lower threshold since patterns are precise multi-word
    # phrases that rarely false-positive, and "no I meant X" yields exactly 1 match (0.70)
    repair = _match_confidence(lower, _REPAIR_PATTERNS)
    if repair >= _REPAIR_CONFIDENCE_THRESHOLD:
        return DirectiveResult(ConversationalDirective.REPAIR, repair)

    # ACKNOWLEDGEMENT — whole-utterance match only (not substring)
    # Strip trailing punctuation for clean lookup
    clean = lower.rstrip(".,!?")
    if clean in _ACKNOWLEDGEMENT_UTTERANCES:
        return DirectiveResult(ConversationalDirective.ACKNOWLEDGEMENT, 0.95)

    # CANCEL — bare single-word denials at high confidence
    # "no stop" normalizes to "no" via denial map; "no" alone must still cancel.
    if clean in _CANCEL_UTTERANCES:
        return DirectiveResult(ConversationalDirective.CANCEL_PENDING, 0.95)

    # CONFIRM — bare confirmations too short to hit pattern threshold
    # e.g. "yes" → 1 pattern match = 0.70 which is below the 0.75 DIRECTIVE threshold;
    # exact-match frozenset ensures these always confirm at 0.95.
    if clean in _CONFIRM_UTTERANCES:
        return DirectiveResult(ConversationalDirective.CONFIRM, 0.95)

    # CORRECT — "no I said X" (before CANCEL so it's not swallowed)
    cor = _match_confidence(lower, _CORRECT_PATTERNS)
    if cor >= DIRECTIVE_CONFIDENCE_THRESHOLD:
        return DirectiveResult(ConversationalDirective.CORRECT, cor)

    # CANCEL_PENDING checked before CONFIRM — "yeah no" → cancel
    cancel = _match_confidence(lower, _CANCEL_PATTERNS)
    confirm = _match_confidence(lower, _CONFIRM_PATTERNS)

    if cancel >= confirm and cancel >= DIRECTIVE_CONFIDENCE_THRESHOLD:
        return DirectiveResult(ConversationalDirective.CANCEL_PENDING, cancel)
    if confirm >= DIRECTIVE_CONFIDENCE_THRESHOLD:
        return DirectiveResult(ConversationalDirective.CONFIRM, confirm)

    rep = _match_confidence(lower, _REPEAT_PATTERNS)
    if rep >= DIRECTIVE_CONFIDENCE_THRESHOLD:
        return DirectiveResult(ConversationalDirective.REPEAT, rep)

    cla = _match_confidence(lower, _CLARIFY_PATTERNS)
    if cla >= DIRECTIVE_CONFIDENCE_THRESHOLD:
        return DirectiveResult(ConversationalDirective.CLARIFY, cla)

    # Return best sub-threshold result (caller decides whether to use it)
    candidates = [
        (ConversationalDirective.CANCEL_PENDING, cancel),
        (ConversationalDirective.CONFIRM, confirm),
        (ConversationalDirective.REPEAT, rep),
        (ConversationalDirective.CLARIFY, cla),
    ]
    best_dir, best_conf = max(candidates, key=lambda x: x[1])
    if best_conf > 0:
        return DirectiveResult(best_dir, best_conf)

    return DirectiveResult(ConversationalDirective.NONE, 0.0)
