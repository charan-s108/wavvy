"""
Issue Classifier — maps customer symptom utterances to specific issue types.

Runs in the LiveKit worker (pure keyword matching, no ML model, no API call).
Called by the orchestrator when the embedding-based workflow trigger returns
no match — customers describe symptoms ("My account is on KYC hold"), not
workflow names ("Fintech Support"), so embedding similarity often misses.

The result selects the correct workflow deterministically rather than leaving
the LLM in GENERAL mode where it improvises and offers escalation.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class IssueType(str, Enum):
    KYC_HOLD           = "kyc_hold"
    FRAUD              = "fraud"
    DISPUTE            = "dispute"
    REFUND             = "refund"
    ACCOUNT_LOCKED     = "account_locked"
    TRANSACTION_STATUS = "transaction_status"
    GENERAL_SUPPORT    = "general_support"


@dataclass
class IssueClassification:
    issue_type:       IssueType
    confidence:       float
    matched_keywords: list[str] = field(default_factory=list)


# Each row: (issue_type, list_of_keyword_phrases, confidence_score)
# Longer / more specific phrases are listed before shorter ones so the first
# match wins the confidence bucket for that issue type.
_PATTERNS: list[tuple[IssueType, list[str], float]] = [
    # ── KYC ──────────────────────────────────────────────────────────────────
    (IssueType.KYC_HOLD, [
        "kyc hold", "kyc verification", "kyc rejected", "kyc pending",
        "kyc failed", "kyc status", "kyc issue", "kyc problem",
        "know your customer", "on hold due to kyc", "account on hold",
        "transaction on hold", "compliance hold",
    ], 0.95),
    (IssueType.KYC_HOLD, ["kyc", "verification hold"], 0.80),

    # ── Fraud Hold Removal — MUST come before generic FRAUD patterns (higher priority) ──
    # Customer already has a fraud hold and wants it lifted — route to Account Unlock
    (IssueType.ACCOUNT_LOCKED, [
        "fraud hold", "fraud investigation hold", "fraud hold on my account",
        "account is hold for fraud", "account is on hold for fraud",
        "my account is hold for a fraud", "account held for fraud",
        "held for fraud investigation", "account under fraud hold",
        "remove fraud hold", "lift fraud hold", "clear fraud hold",
        "held due to fraud", "held because of fraud",
        "fraud is on hold", "account has a fraud hold",
    ], 0.95),

    # ── Fraud ─────────────────────────────────────────────────────────────────
    (IssueType.FRAUD, [
        "unauthorized transaction", "someone used my account", "i didn't make",
        "i did not make", "not authorized", "fraudulent", "account hacked",
        "account compromised", "someone else used", "report fraud",
        "didn't authorize", "did not authorize",
    ], 0.95),
    (IssueType.FRAUD, ["fraud", "unauthorized", "stolen card", "hacked", "suspicious"], 0.80),

    # ── Dispute ───────────────────────────────────────────────────────────────
    (IssueType.DISPUTE, [
        "raise a dispute", "file a dispute", "wrong amount charged",
        "charged twice", "duplicate charge", "merchant didn't deliver",
        "overcharged", "billing error", "wrong charge",
    ], 0.95),
    (IssueType.DISPUTE, ["dispute", "overcharged", "incorrect amount"], 0.75),

    # ── Refund ────────────────────────────────────────────────────────────────
    (IssueType.REFUND, [
        "refund request", "want a refund", "need a refund", "money back",
        "money not returned", "money was deducted", "failed transaction refund",
        "get my money back", "send my money back", "give me a refund",
        "process the refund", "can you refund", "i want my money",
        "process a refund", "initiate a refund", "raise a refund",
        "transaction failed refund", "payment failed refund",
        "amount was deducted", "amount got deducted", "money got deducted",
        "deducted from my account", "deducted but", "got debited",
        "debited but not", "debited and failed",
        # Colloquial: "money got deducted and it got failed"
        "deducted and got failed", "deducted and it failed",
        "got failed and money", "failed and money deducted",
    ], 0.95),
    (IssueType.REFUND, ["refund", "reimburs"], 0.75),

    # ── Account locked ────────────────────────────────────────────────────────
    (IssueType.ACCOUNT_LOCKED, [
        "can't log in", "cannot login", "account locked", "account blocked",
        "account suspended", "account disabled", "locked out of",
        "access denied", "restore access", "unable to access",
    ], 0.95),
    (IssueType.ACCOUNT_LOCKED, ["locked", "blocked", "suspended"], 0.70),

    # ── Transaction status ────────────────────────────────────────────────────
    (IssueType.TRANSACTION_STATUS, [
        "transaction status", "payment status", "did my payment go through",
        "payment not received", "transfer pending", "transaction pending",
        "where is my money", "money not received", "payment stuck",
        "transfer stuck", "transaction stuck",
    ], 0.90),
    (IssueType.TRANSACTION_STATUS, [
        "transaction failed", "payment failed", "transfer failed",
        # Colloquial Indian English: "it got failed", "transaction got failed"
        "got failed", "it failed", "transaction got failed",
        "payment got failed", "transfer got failed",
    ], 0.80),
    (IssueType.TRANSACTION_STATUS, ["transaction", "payment"], 0.65),

    # ── General (lowest priority catch-all) ───────────────────────────────────
    (IssueType.GENERAL_SUPPORT, [
        "help with my account", "account issue", "account problem",
        "having trouble", "need support", "something wrong with my account",
    ], 0.70),
    (IssueType.GENERAL_SUPPORT, ["account", "issue", "problem"], 0.50),
]

# Precompile all keyword phrases as \bphrase\b regex patterns.
# Word boundaries prevent "unlocked" from matching "locked",
# "unblocked" from matching "blocked", etc.
_COMPILED_PATTERNS: list[tuple[IssueType, list[tuple[str, re.Pattern]], float]] = [
    (
        issue_type,
        [(kw, re.compile(r"\b" + re.escape(kw) + r"\b")) for kw in keywords],
        confidence,
    )
    for issue_type, keywords, confidence in _PATTERNS
]

# Workflow UUIDs from seed.py — deterministic mapping from issue to entry point
_ISSUE_TO_WORKFLOW_ID: dict[IssueType, str] = {
    IssueType.KYC_HOLD:             "00000000-0000-0000-0000-000000000001",  # Fintech Support
    IssueType.FRAUD:                "00000000-0000-0000-0000-000000000005",  # Fraud Report
    IssueType.DISPUTE:              "00000000-0000-0000-0000-000000000004",  # Dispute Filing
    IssueType.REFUND:               "00000000-0000-0000-0000-000000000003",  # Refund Request
    IssueType.ACCOUNT_LOCKED:       "00000000-0000-0000-0000-000000000006",  # Account Unlock
    IssueType.TRANSACTION_STATUS:   "00000000-0000-0000-0000-000000000002",  # Transaction Status
    IssueType.GENERAL_SUPPORT:      "00000000-0000-0000-0000-000000000001",  # Fintech Support
}

# Minimum confidence required to act on a classification
CONFIDENCE_THRESHOLD = 0.60

# Completion-context signals per issue type.
# If ANY signal is found in the utterance, the keyword match is suppressed —
# the customer is describing a RESOLVED state, not making a new request.
# This prevents "refund has been initiated" from triggering a Refund workflow,
# and "account is now unlocked" from triggering an Account Unlock workflow.
_COMPLETION_SIGNALS: dict[IssueType, list[str]] = {
    IssueType.REFUND: [
        "refund has been",
        "refund was",
        "refund is done",
        "refund is complete",
        "refund processed",
        "refund initiated",
        "refund reference",
        "already initiated",
        "already got my refund",
        "already refunded",
        "refund in progress",
        "refund is in progress",
        "got the refund",
        "received the refund",
    ],
    IssueType.ACCOUNT_LOCKED: [
        "account is now unlocked",
        "account has been unlocked",
        "account was unlocked",
        "now have access",
        "able to log in",
        "able to login",
        "can log in now",
        "can login now",
        "account unblocked",
    ],
    IssueType.DISPUTE: [
        "dispute has been",
        "dispute was filed",
        "dispute filed",
        "dispute raised",
        "dispute reference",
        "already raised a dispute",
        "already filed",
    ],
    IssueType.FRAUD: [
        "fraud case",
        "fraud has been reported",
        "fraud was reported",
        "fraud report filed",
        "already reported",
        "case has been opened",
        "fraud reference",
    ],
}

# Precompile completion signals as substring checks (no word boundary needed —
# these are full phrases, not single keywords).
_COMPILED_COMPLETION_SIGNALS: dict[IssueType, list[re.Pattern]] = {
    issue_type: [re.compile(re.escape(signal)) for signal in signals]
    for issue_type, signals in _COMPLETION_SIGNALS.items()
}


# Universal closure phrases — positive-sentiment wrap-up language that signals
# the conversation is ending, not starting a new request.  Only applied when
# the best keyword match scores ≤ 0.75 (weak signal).  A 0.95-confidence
# specific request phrase ("I want a refund for a different transaction") still
# routes correctly even if the customer also says "thank you".
_UNIVERSAL_CLOSURE_PHRASES: frozenset[str] = frozenset([
    "thank you", "thanks", "thank you so much", "many thanks",
    "that's all", "thats all", "that's everything", "nothing else",
    "all set", "all good", "i'm good", "im good", "we're done", "were done",
    "got it", "got the message", "got the reference",
    "perfect", "great", "wonderful", "excellent", "awesome",
    "resolved", "fixed", "sorted", "done", "it's working", "its working",
    "working now", "it works", "it worked",
    "have a good day", "have a great day", "goodbye", "bye", "bye bye",
    "take care", "see you",
])

_COMPILED_CLOSURE_PHRASES: list[re.Pattern] = [
    re.compile(r"\b" + re.escape(phrase) + r"\b")
    for phrase in _UNIVERSAL_CLOSURE_PHRASES
]

# Negation words — used to suppress single-word keyword matches that appear in
# a negated context ("no fraud", "I don't see any fraud", "there is no fraud").
# Only applied to single-word keywords (no spaces) — multi-word intent phrases
# like "I didn't make this transaction" are inherently intentional and unambiguous.
_NEGATION_WORDS: frozenset[str] = frozenset([
    "no", "not", "never", "none", "without",
    "don't", "dont", "doesn't", "doesnt", "didn't", "didnt",
    "isn't", "isnt", "wasn't", "wasnt", "weren't", "werent",
    "haven't", "havent", "hasn't", "hasnt", "hadn't", "hadnt",
    "won't", "wont", "wouldn't", "wouldnt", "can't", "cant", "couldn't", "couldnt",
])

_STRIP_PUNCT = re.compile(r"[^\w']+")


def _is_single_keyword_negated(lower: str, keyword: str) -> bool:
    """Return True if `keyword` (no spaces) appears within 8 words of a negation."""
    if ' ' in keyword:
        return False  # phrase keywords are intentional — skip negation check
    kw_re = re.compile(r'\b' + re.escape(keyword) + r'\b')
    for m in kw_re.finditer(lower):
        prefix = lower[max(0, m.start() - 60):m.start()]
        preceding = [_STRIP_PUNCT.sub('', w) for w in prefix.split()[-8:]]
        if any(w in _NEGATION_WORDS for w in preceding):
            return True
    return False


def _is_completion_context(lower: str, issue_type: IssueType) -> bool:
    """Return True if the utterance describes a resolved outcome, not a new request."""
    for pattern in _COMPILED_COMPLETION_SIGNALS.get(issue_type, []):
        if pattern.search(lower):
            return True
    return False


def _is_closure_utterance(lower: str) -> bool:
    """Return True if the utterance is primarily wrap-up / gratitude language."""
    return any(p.search(lower) for p in _COMPILED_CLOSURE_PHRASES)


def classify_issue(text: str) -> IssueClassification | None:
    """Classify a customer utterance into a known issue type.

    Scans _PATTERNS in order — higher-confidence rows first per issue type.
    Returns the highest-confidence match, or None if nothing clears
    CONFIDENCE_THRESHOLD.

    Never raises.
    """
    lower = text.lower()
    best: tuple[IssueType, float, list[str]] | None = None

    for issue_type, kw_patterns, confidence in _COMPILED_PATTERNS:
        matched = [kw for kw, pattern in kw_patterns if pattern.search(lower)]
        if not matched:
            continue
        # Remove single-word keywords that appear in a negated context.
        # "I don't see any fraud" / "there is no fraud" → suppress "fraud" match.
        # Multi-word phrases (e.g. "i didn't make this") are kept — they encode intent.
        active = [kw for kw in matched if not _is_single_keyword_negated(lower, kw)]
        if not active:
            logger.debug(
                "issue_classifier: suppressed %s — all keywords negated in: %r",
                issue_type.value, text[:80],
            )
            continue
        matched = active
        if best is None or confidence > best[1]:
            best = (issue_type, confidence, matched)

    if best is None or best[1] < CONFIDENCE_THRESHOLD:
        logger.debug("issue_classifier: no match above threshold for: %r", text[:80])
        return None

    issue_type, confidence, matched_keywords = best

    # Suppress if the utterance is describing a completed/resolved state, not a new request.
    if _is_completion_context(lower, issue_type):
        logger.debug(
            "issue_classifier: suppressed %s — completion context detected: %r",
            issue_type.value, text[:80],
        )
        return None

    # Suppress weak matches (≤ 0.75) when the utterance is primarily closure language.
    # Strong matches (0.95) survive even with gratitude — e.g. "thank you but I also
    # want a refund for a different transaction" still routes correctly.
    if confidence <= 0.75 and _is_closure_utterance(lower):
        logger.debug(
            "issue_classifier: suppressed %s (confidence=%.2f) — closure language: %r",
            issue_type.value, confidence, text[:80],
        )
        return None

    logger.info(
        "issue_classifier: type=%s confidence=%.2f keywords=%s utterance=%r",
        issue_type.value, confidence, matched_keywords, text[:80],
    )
    return IssueClassification(
        issue_type=issue_type,
        confidence=confidence,
        matched_keywords=matched_keywords,
    )


def get_workflow_id_for_issue(issue_type: IssueType) -> str | None:
    """Return the workflow UUID for a classified issue type."""
    return _ISSUE_TO_WORKFLOW_ID.get(issue_type)
