"""
Entity extractor — deterministic, pre-LLM, <1ms per utterance.

Runs on every raw STT string before the orchestrator dispatches.
Writes extracted values into session.orchestrator_state.entity_slots.

Phone is accumulated across turns: the customer may say digits slowly or
across multiple STT chunks.  The extractor appends new digits to a side-channel
buffer keyed by object id of the EntitySlots instance and commits slots.phone
only when the total reaches _PHONE_MIN_DIGITS.

All normalization helpers are imported from agent_tools — not duplicated here.
"""
from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from session.orchestrator_state import EntitySlots
from voice.agent_tools import (
    _normalize_phone,
    _normalize_otp,
    _normalize_txn_id,
    _PHONE_WORD_MAP,  # imported so callers can reference it; not used directly here
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

_PHONE_MIN_DIGITS = 10

# TXN-ID: require explicit TXN prefix — bare digit sequences cause false positives
# on phone numbers, prices, and dates.  Customers always say "TXN-1234".
_TXN_PATTERN = re.compile(r'\b(?:TXN|TRX)[-\s]?\d{4,6}\b', re.IGNORECASE)

# Used by _looks_phone_like to detect word-digits ("nine", "oh", etc.)
_WORD_DIGIT_RE = re.compile(
    r'\b(?:zero|oh|one|two|three|four|five|six|seven|eight|nine)\b',
    re.IGNORECASE,
)
_NUMERIC_RE = re.compile(r'\d')
# Fast membership test used by the consecutive-run check
_WORD_DIGIT_SET = frozenset([
    "zero", "oh", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"
])

# Side-channel: partial digit buffers keyed by id(EntitySlots).
# We never set slots.phone until >= _PHONE_MIN_DIGITS digits are collected so
# that None still means "not yet collected".
_partial_phone: dict[int, str] = {}


# ── Public API ────────────────────────────────────────────────────────────────

def extract_entities(text: str, slots: EntitySlots) -> EntitySlots:
    """Extract phone, OTP, and TXN-ID from a raw STT utterance.

    Mutates `slots` in place and returns it.
    """
    _update_phone(text, slots)
    _update_otp(text, slots)
    _update_txn_id(text, slots)
    return slots


def clear_phone_buffer(slots: EntitySlots) -> None:
    """Reset phone accumulation when a node resets or workflow exits."""
    slots.phone = None
    _partial_phone.pop(id(slots), None)


# ── Phone accumulation ────────────────────────────────────────────────────────

def _looks_phone_like(text: str) -> bool:
    """Return True only if the utterance plausibly contains phone digits.

    Literal numeric chars are always accepted.  For word-digits ("nine", "two", …)
    we require a run of ≥2 CONSECUTIVE word-digits.  This rejects quantity phrases
    like "three to four days" (max consecutive run = 1) while accepting genuine
    phone dictation like "nine eight seven" (consecutive run = 3).
    """
    if _NUMERIC_RE.search(text):
        return True
    words = [re.sub(r"[^a-z]", "", w.lower()) for w in text.split()]
    run = 0
    for w in words:
        if w in _WORD_DIGIT_SET:
            run += 1
            if run >= 2:
                return True
        else:
            run = 0
    return False


def _update_phone(text: str, slots: EntitySlots) -> None:
    if slots.phone is not None:
        return  # already committed

    if not _looks_phone_like(text):
        return  # lone number word in non-numeric context — not phone dictation

    normalized = _normalize_phone(text)
    new_digits  = re.sub(r'\D', '', normalized)
    if not new_digits:
        return

    # If the utterance alone contains a complete phone number, commit it directly
    # without merging with any partial buffer.  This prevents garbled 18-digit
    # numbers when a customer types a full number after partially dictating digits.
    if len(new_digits) >= _PHONE_MIN_DIGITS:
        committed = ('+' + new_digits) if len(new_digits) >= 11 else new_digits
        slots.phone = committed
        _partial_phone.pop(id(slots), None)
        logger.debug("entity_extractor: phone committed (%d digits, single utterance)", len(new_digits))
        return

    existing = _partial_phone.get(id(slots), "")
    merged   = existing + new_digits

    if len(merged) >= _PHONE_MIN_DIGITS:
        committed = ('+' + merged) if len(merged) >= 11 else merged
        slots.phone = committed
        _partial_phone.pop(id(slots), None)
        logger.debug("entity_extractor: phone committed (%d digits, accumulated)", len(merged))
    else:
        _partial_phone[id(slots)] = merged
        logger.debug(
            "entity_extractor: phone buffer %d/%d digits",
            len(merged), _PHONE_MIN_DIGITS,
        )


# ── OTP extraction ────────────────────────────────────────────────────────────

def _update_otp(text: str, slots: EntitySlots) -> None:
    """OTP does not accumulate — the customer reads all 6 digits in one utterance."""
    if slots.otp is not None:
        return

    normalized = _normalize_otp(text)
    if len(normalized) == 6:
        slots.otp = normalized
        logger.debug("entity_extractor: OTP committed")


# ── Transaction ID extraction ─────────────────────────────────────────────────

def _update_txn_id(text: str, slots: EntitySlots) -> None:
    if slots.txn_id is not None:
        return

    match = _TXN_PATTERN.search(text.upper())
    if match:
        candidate = _normalize_txn_id(match.group(0))
        if candidate.startswith("TXN-"):
            slots.txn_id = candidate
            logger.debug("entity_extractor: TXN-ID committed → %s", candidate)
