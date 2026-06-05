"""
Post-LLM response cleanup and streaming chunking policy for TTS delivery.

speech_chunking_policy() — controls when to flush the LLM token buffer to TTS.
apply_response_policy()  — post-flush cleanup: strips markdown, removes unsafe promises.
"""
import re

MAX_SENTENCES = 2

_MARKDOWN_PATTERNS = [
    (re.compile(r'\*{1,2}([^*]+)\*{1,2}'), r'\1'),   # bold/italic → text
    (re.compile(r'#{1,6}\s+'), ''),                    # headers
    (re.compile(r'`([^`]+)`'), r'\1'),                 # inline code
    (re.compile(r'```[\s\S]*?```'), ''),               # code blocks
    (re.compile(r'^\s*[-*+]\s+', re.MULTILINE), ''),  # bullet points
    (re.compile(r'^\s*\d+\.\s+', re.MULTILINE), ''), # numbered lists
    (re.compile(r'\[([^\]]+)\]\([^\)]+\)'), r'\1'),   # links → label
    (re.compile(r'\|[^\n]+\|'), ''),                  # tables
]

_UNSAFE_PROMISES = [
    r"i'?ll call you back",
    r"we will email you",
    r"you'?ll receive",
    r"we'?ll follow up",
    r"you will get a",
    r"i'?ll send you an email",
]
_UNSAFE_PROMISE_RE = re.compile(
    '|'.join(_UNSAFE_PROMISES), re.IGNORECASE
)

# Normalize voice phrasing
_VOICE_REPLACEMENTS = [
    (re.compile(r'\be\.g\.\b', re.IGNORECASE), 'for example'),
    (re.compile(r'\bi\.e\.\b', re.IGNORECASE), 'that is'),
    (re.compile(r'\betc\.\b', re.IGNORECASE), 'and so on'),
    (re.compile(r'\bvsz?\.\s+', re.IGNORECASE), 'versus '),
]


def strip_markdown(text: str) -> str:
    for pattern, replacement in _MARKDOWN_PATTERNS:
        text = pattern.sub(replacement, text)
    # Collapse multiple spaces/newlines
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def remove_unsafe_promises(text: str) -> str:
    """Remove unverifiable future promises from AI responses."""
    return _UNSAFE_PROMISE_RE.sub('', text)


def enforce_max_sentences(text: str, n: int = MAX_SENTENCES) -> str:
    """Keep only the first n sentences."""
    # Split on sentence-ending punctuation followed by space or end
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    return ' '.join(sentences[:n]).strip()


def normalize_voice_phrasing(text: str) -> str:
    for pattern, replacement in _VOICE_REPLACEMENTS:
        text = pattern.sub(replacement, text)
    return text


def speech_chunking_policy(buf: str, is_final: bool = False) -> tuple[str, str]:
    """
    Decide when to flush the LLM token accumulation buffer to TTS.
    Returns (phrase_to_speak, remaining_buffer).
    Empty phrase string means "not ready to flush yet".

    Rules (in priority order):
    1. Never flush mid-acronym — wait for the word to complete
    2. Never flush mid-number — wait for the numeric phrase to complete
    3. Never flush on a dangling preposition — clause is semantically incomplete
    4. Flush on sentence boundary
    5. Flush on comma boundary (only if clause ≥ 20 chars, avoids "Hi,")
    6. Latency guard — flush at word boundary if buffer exceeds 80 chars
    7. Final flush — end of stream
    """

    # 1. Never flush mid-acronym (all-caps run at end of buffer)
    if re.search(r'\b[A-Z]{2,}\s*$', buf):
        return "", buf

    # 2. Never flush mid-number
    if re.search(r'\b(?:\d+[-\s]?|hundred|thousand|million)\s*$', buf, re.I):
        return "", buf

    # 3. Never flush on a dangling preposition — clause is semantically incomplete
    #    "Wavvy supports integrations with" → wait for the noun
    if re.search(r'\b(with|for|to|into|using|from|of|on|at|by|about)\s*$', buf, re.I):
        return "", buf

    # 4. Sentence boundary (highest priority flush)
    # Match punctuation followed by whitespace OR end-of-string
    m = re.search(r'[.!?](?:\s+|$)', buf)
    if m:
        return buf[:m.end()].strip(), buf[m.end():]

    # 5. Comma boundary — only if clause is ≥ 60 chars.
    # 20-char threshold was too low: short intros like "I'm happy to help you with Wavvy,"
    # (34 chars) flushed mid-clause, creating the fragmented TTS artifact reported
    # ("I'm happy to help you with Wavvy," / "a real-time voice AI platform..." / ...).
    m = re.search(r',\s+', buf)
    if m and m.start() >= 60:
        return buf[:m.end()].strip(), buf[m.end():]

    # 6. Latency guard — buffer getting long, find nearest word boundary
    if len(buf) > 80:
        space = buf.rfind(' ', 40, 80)
        if space > 0:
            return buf[:space].strip(), buf[space:]

    # 7. Final flush — end of stream
    if is_final and buf.strip():
        return buf.strip(), ""

    return "", buf


def _temperature_for_kb(kb_relevance: float | None) -> float:
    """
    Dynamic LLM temperature based on KB retrieval confidence.
    Low KB confidence → minimize hallucination risk with lower temperature.
    """
    if kb_relevance is None or kb_relevance < 0.3:
        return 0.1   # low KB confidence: cautious, minimize hallucination
    if kb_relevance < 0.7:
        return 0.25  # moderate confidence: balanced
    return 0.4       # high confidence: allow natural variation


def apply_response_policy(
    text: str,
    tool_result_missing: bool = False,
    max_sentences: int = MAX_SENTENCES,
) -> str:
    """
    Full cleanup pipeline — called on every LLM response before TTS.
    tool_result_missing=True means tool execution failed; return safe fallback immediately.
    """
    if tool_result_missing:
        return "I couldn't complete that. Let me try again."

    if not text or not text.strip():
        return None

    text = strip_markdown(text)
    text = remove_unsafe_promises(text)
    text = normalize_voice_phrasing(text)
    text = enforce_max_sentences(text, n=max_sentences)
    return text.strip()
