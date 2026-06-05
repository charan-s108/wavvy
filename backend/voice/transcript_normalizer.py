"""
Layer 1, Step 0: Transcript normalization.
Runs BEFORE identity guard, directive detector, intent router, and entity extractor.
Produces stable, canonical text from noisy STT output.
"""
import re
import logging

logger = logging.getLogger(__name__)

FILLER_WORDS = {
    "uh", "um", "er", "ah", "hmm",
    "uhh", "umm", "err", "ahh", "hm", "erm", "mhm",
    # "right", "like", "you know" removed — too semantically loaded mid-phrase
    # ("that's not right", "I like wavvy", "you know what I mean" all break with stripping)
}

AFFIRMATIVE_MAP = {
    "yeah": "yes", "yep": "yes", "yup": "yes", "yea": "yes",
    "sure": "yes", "absolutely": "yes", "definitely": "yes",
    "of course": "yes", "go ahead": "yes", "do it": "yes",
    "ok": "yes", "okay": "yes", "alright": "yes", "affirmative": "yes",
    "mmhm": "yes", "mhm": "yes", "uh huh": "yes", "uh-huh": "yes",
}

DENIAL_MAP = {
    "nah": "no", "nope": "no", "no way": "no", "never mind": "no",
    "nevermind": "no", "cancel that": "no", "forget it": "no",
    "dont": "no", "don't": "no", "stop": "no", "wait": "no",
}

# Spoken digit words → digit characters
DIGIT_WORD_MAP = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
    "oh": "0",  # "oh" is commonly used for zero in phone/OTP contexts
}

# Spoken number words (for order IDs)
NUMBER_WORD_MAP = {
    **DIGIT_WORD_MAP,
    "ten": "10", "eleven": "11", "twelve": "12", "thirteen": "13",
    "fourteen": "14", "fifteen": "15", "sixteen": "16", "seventeen": "17",
    "eighteen": "18", "nineteen": "19", "twenty": "20", "thirty": "30",
    "forty": "40", "fifty": "50", "sixty": "60", "seventy": "70",
    "eighty": "80", "ninety": "90", "hundred": "100",
}


def _strip_fillers(text: str) -> str:
    words = text.split()
    result = [w for w in words if w.lower() not in FILLER_WORDS]
    # Also strip multi-word fillers via regex
    cleaned = " ".join(result)
    cleaned = re.sub(r'\b(you know|I mean|sort of|kind of)\b', '', cleaned, flags=re.IGNORECASE)
    return re.sub(r'\s+', ' ', cleaned).strip()


def _collapse_repetitions(text: str) -> str:
    # "yeah yeah yeah" → "yeah"; "stop stop" → "stop"
    return re.sub(r'\b(\w+)(\s+\1){2,}\b', r'\1', text, flags=re.IGNORECASE)


def _normalize_affirmatives_denials(text: str) -> str:
    # Skip replacement for 3+ word utterances — they may be repair phrases like
    # "no I meant pricing" or "no I said I don't want a demo".  Full-text replacement
    # on multi-word utterances destroys the repair signal before directive detection runs.
    if len(text.split()) > 2:
        return text
    lower = text.lower().strip()

    # Exact whole-utterance match first (highest priority — avoids component false matches)
    # e.g. "okay cool" must NOT collapse to "yes" just because "okay" is an affirmative.
    if lower in DENIAL_MAP:
        return DENIAL_MAP[lower]
    if lower in AFFIRMATIVE_MAP:
        return AFFIRMATIVE_MAP[lower]

    # Partial match: DENIAL only (contains check) — for "no way", "never mind", "stop it"
    # AFFIRMATIVE does NOT do partial matching: "okay cool" → stays as-is (ACKNOWLEDGEMENT)
    for phrase, replacement in DENIAL_MAP.items():
        if re.search(r'\b' + re.escape(phrase) + r'\b', lower):
            return replacement

    return text


def _normalize_spoken_digits(text: str) -> str:
    """
    Convert spoken digit sequences to numeric strings.
    "one two three four five six" → "123456"
    Applied only to sequences of digit words (for OTP / phone context).
    """
    tokens = text.lower().split()
    result_tokens = []
    digit_run = []

    for token in tokens:
        clean = re.sub(r'[^\w]', '', token)
        if clean in DIGIT_WORD_MAP:
            digit_run.append(DIGIT_WORD_MAP[clean])
        else:
            if digit_run:
                if len(digit_run) >= 4:  # only collapse runs of 4+ digits (OTP/phone)
                    result_tokens.append("".join(digit_run))
                else:
                    result_tokens.extend(digit_run)
                digit_run = []
            result_tokens.append(token)

    if digit_run:
        if len(digit_run) >= 4:
            result_tokens.append("".join(digit_run))
        else:
            result_tokens.extend(digit_run)

    return " ".join(result_tokens)


def _strip_trailing_artifacts(text: str) -> str:
    # Remove trailing punctuation STT artifacts
    return re.sub(r'[.,!?;:]+$', '', text).strip()


def normalize_transcript(text: str) -> str:
    """
    Full normalization pipeline. Run before all downstream processors.
    Never raises — returns original text on any failure.
    """
    if not text or not text.strip():
        return text
    try:
        t = text.strip()
        t = _correct_brand_names(t)        # fix STT misrecognitions first
        t = _strip_fillers(t)
        t = _collapse_repetitions(t)
        t = _normalize_affirmatives_denials(t)
        t = _normalize_spoken_digits(t)
        t = normalize_hinglish(t)
        t = _strip_trailing_artifacts(t)
        return t if t else text
    except Exception as exc:
        logger.warning(f"normalize_transcript failed: {exc}")
        return text


# ── Brand-name STT corrections ───────────────────────────────────────────────
# Deepgram phonetic near-misses for "Wavvy" observed in production.
# Applied BEFORE intent routing so downstream classifiers always see the
# canonical spelling. Patterns are narrow whole-word matches to avoid
# clobbering unrelated words.
#
# Confirmed misrecognitions reported:
#   "bobby"  — bilabial W→B shift + vowel drift (/ˈwævi/ → /ˈbɒbi/)
#   "wavy"   — dropped second 'v' (common English word, safe to upcase in context)
#   "wavi"   — alternate romanisation
#   "wavey"  — alternate spelling
# NOTE: "llm" is intentionally NOT corrected here — it is a valid tech term
# the user may genuinely say, and adding it would cause destructive replacements.
_STT_BRAND_CORRECTIONS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'\bboby\b|\bbobby\b',       re.IGNORECASE), 'Wavvy'),
    (re.compile(r'\bwavi\b|\bwavey\b',       re.IGNORECASE), 'Wavvy'),
    # "wavy" alone → "Wavvy" only when it is the entire utterance or surrounded
    # by stop words, to avoid clobbering "wavy hair", "wavy lines" etc.
    (re.compile(r'(?:^|\s)wavy(?:\s|$)',     re.IGNORECASE),
     lambda m: m.group(0).replace(m.group(0).strip(), 'Wavvy')),
]


def _correct_brand_names(text: str) -> str:
    for pattern, replacement in _STT_BRAND_CORRECTIONS:
        if callable(replacement):
            text = pattern.sub(replacement, text)
        else:
            text = pattern.sub(replacement, text)
    return text


# ── Hinglish normalization ────────────────────────────────────────────────────

# Phrase-level only — no single-token deletions.
# Single-token deletions cause destructive false matches:
#   "only enterprise" → "enterprise" (breaks meaning)
#   bare r'\bna\b' → matches "banana", "enable", "NAT"
#
# Safe rules:
#   - Multi-word phrases with unambiguous word boundaries
#   - Sentence-final markers anchored to end-of-string (\s+na\s*$)
_HINGLISH_MAP: list[tuple[str, str]] = [
    # IMPORTANT: compound phrases must precede their component tokens.
    # e.g. \bnahi\s+chahiye\b MUST come before \bchahiye\b and \bnahi\b
    # so that "nahi chahiye" → "do not want" and not "no I want".
    (r'\bkarna\s+hai\b',          'want to'),
    (r'\bkya\s+hai\b',            'what is'),
    (r'\bbatao\s+mujhe\b',        'tell me'),
    (r'\bbatao\b',                'tell me'),
    (r'\bnahi\s+chahiye\b',       'do not want'),   # before \bchahiye\b
    (r'\bchahiye\s+mujhe\b',      'I want'),
    (r'\bchahiye\b',              'I want'),
    (r'\bsakte\s+ho\b',           'can you'),
    (r'\bsakte\s+hai\b',          'can you'),
    (r'\bnahi\b',                 'no'),             # after \bnahi\s+chahiye\b
    (r'\bhaan\s+ji\b',            'yes'),
    (r'\bhaan\b',                 'yes'),
    (r'\bacha\s+ji\b',            'okay'),
    (r'\bacha\b',                 'okay'),
    (r'\bthik\s+hai\b',           'okay'),
    (r'\bthik\b',                 'okay'),
    (r'\bsamjha\b',               'understood'),
    (r'\bsamajh\s+gaya\b',        'understood'),
    (r'\bmajha\s+aaya\b',         'makes sense'),
    # Sentence-final confirmation marker — ONLY at end of string to avoid "banana"
    (r'\s+na\s*\??\s*$',          '?'),
    (r'\s+na\s*$',                ''),
]


def normalize_hinglish(text: str) -> str:
    """
    Normalize common Hinglish phrases to English equivalents.
    Phrase-level only — never deletes single tokens to avoid false matches.
    Called as the final step in normalize_transcript().
    Logs original → normalized when a change occurs (for debuggability).
    """
    original = text
    for pattern, replacement in _HINGLISH_MAP:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    text = text.strip()
    if text != original:
        logger.debug(f"hinglish_normalized: {original!r} → {text!r}")
    return text
