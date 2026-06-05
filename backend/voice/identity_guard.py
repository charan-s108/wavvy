"""
Layer 1, Step 1: Wavvy name confusion detection and correction.
Uses phonetic similarity (Levenshtein ratio + Soundex) — no static word map.
Policy: one spoken correction per call, then silent normalization.
"""
import re
import logging

logger = logging.getLogger(__name__)

SIMILARITY_THRESHOLD = 0.72   # catches 1-2 edit variants against 5-char "wavvy"
TARGET_NAME = "wavvy"

# Words to ignore — these are correct spellings, not confusion
_EXACT_OR_ACCEPTABLE = {"wavvy", "wavy"}

# Explicit STT mishearings of "wavvy" that score below the Levenshtein threshold
# due to short string length (4-char vs 5-char) but are phonetically close.
# m/r/n↔w labial/rhotic confusion is the most common source.
_KNOWN_VARIANTS = frozenset({
    "mavi", "mavvy", "ravi", "ravvy", "navi", "navvy",
    "vavi", "wavi", "wavie", "wavvi", "wavee", "wavey",
    "bobby", "wabi", "wappy", "wabe", "avi", "avvy",
})


def _soundex(word: str) -> str:
    word = word.upper().strip()
    if not word:
        return "0000"
    result = word[0]
    mapping = {
        "BFPV": "1", "CGJKQSXYZ": "2", "DT": "3",
        "L": "4", "MN": "5", "R": "6",
    }
    prev_code = ""
    for ch in word[1:]:
        code = ""
        for chars, val in mapping.items():
            if ch in chars:
                code = val
                break
        if code and code != prev_code:
            result += code
        prev_code = code
    return (result + "000")[:4]


def _levenshtein_ratio(a: str, b: str) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    la, lb = len(a), len(b)
    dp = list(range(lb + 1))
    for i in range(1, la + 1):
        prev = dp[:]
        dp[0] = i
        for j in range(1, lb + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            dp[j] = min(dp[j] + 1, dp[j - 1] + 1, prev[j - 1] + cost)
    distance = dp[lb]
    return 1.0 - distance / max(la, lb)


def _phonetic_similarity(word: str, target: str) -> float:
    w = word.lower().strip(r""".,!?;:'"()""")
    t = target.lower()

    # Exact match
    if w == t:
        return 1.0

    # Levenshtein similarity
    lev = _levenshtein_ratio(w, t)

    # Soundex match bonus
    soundex_match = 0.1 if _soundex(w) == _soundex(t) else 0.0

    return min(lev + soundex_match, 1.0)


def _is_wavvy_confusion(word: str) -> bool:
    """True if word is a known STT mishearing or Levenshtein-similar to 'wavvy'."""
    clean = word.lower().strip(".,!?;:'\"()")
    if clean in _EXACT_OR_ACCEPTABLE:
        return False
    if clean in _KNOWN_VARIANTS:
        return True
    return _phonetic_similarity(clean, TARGET_NAME) >= SIMILARITY_THRESHOLD


def apply_identity_guard(text: str, session) -> tuple[str, str | None]:
    """
    Returns (normalized_text, None).
    Replaces every word that is a known or detected mishearing of "Wavvy" with "Wavvy".
    Replacement is always silent — never speaks a correction to the customer.
    """
    tokens = text.split()
    result = []
    confused = False
    for token in tokens:
        if _is_wavvy_confusion(token):
            confused = True
            # Preserve trailing punctuation attached to the word
            core = token.lower().strip(".,!?;:'\"()")
            replaced = re.sub(re.escape(core), "Wavvy", token, flags=re.IGNORECASE, count=1)
            result.append(replaced)
        else:
            result.append(token)

    if not confused:
        return text, None

    session.identity_corrected = True
    return " ".join(result), None
