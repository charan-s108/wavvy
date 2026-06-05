"""
Builds the minimal LLM payload from session state.
LLM receives: system prompt + conversational context + optional memory + optional KB + utterance.
No conversation history replay — ConversationalContext.to_compact() is the memory abstraction.
"""
import logging
import re

logger = logging.getLogger(__name__)

MAX_TOKENS = 2000
KB_MAX_CHARS = 1200      # hard cap before sanitize
# KB search uses RRF fusion — scores range ~0.01–0.05, not 0–1 cosine similarity.
# A threshold of 0.4 (cosine scale) would reject every result. Use 0.01 to accept
# any result with meaningful signal; near-zero scores indicate no real hit.
KB_RELEVANCE_THRESHOLD = 0.01  # skip KB injection below this score


# ── KB sanitization ───────────────────────────────────────────────────────────

_STRIP_PATTERNS = [
    re.compile(r'```[\s\S]*?```'),          # code blocks
    re.compile(r'`[^`]+`'),                  # inline code
    re.compile(r'^#{1,6}\s+', re.MULTILINE), # markdown headers
    re.compile(r'\*{1,2}([^*]+)\*{1,2}'),   # bold/italic → keep text
    re.compile(r'^\s*[-*+]\s+', re.MULTILINE), # list markers
    re.compile(r'^\s*\d+\.\s+', re.MULTILINE), # numbered lists
    re.compile(r'\[([^\]]+)\]\([^\)]+\)'),   # links → keep label
    re.compile(r'<!-.*?-->', re.DOTALL),     # HTML comments
    re.compile(r'<[^>]+>'),                  # HTML tags
]

_SYSTEM_INSTRUCTION_PATTERN = re.compile(
    r'(?i)(system:|assistant:|<system>|you are|your role is|instructions:)',
)


def truncate_kb_chunk(chunk: str) -> str:
    return chunk[:KB_MAX_CHARS]


def sanitize_kb_chunk(chunk: str) -> str:
    """Strip markdown, HTML, code blocks, and system instructions from KB content."""
    text = chunk
    for pattern in _STRIP_PATTERNS:
        text = pattern.sub(r'\1' if pattern.groups else '', text)

    # Remove lines containing system instructions
    lines = [
        line for line in text.splitlines()
        if not _SYSTEM_INSTRUCTION_PATTERN.search(line)
    ]
    text = ' '.join(' '.join(lines).split())
    return text.strip()


def process_kb_chunk(chunk: str) -> str:
    """Correct order: truncate FIRST, sanitize SECOND."""
    return sanitize_kb_chunk(truncate_kb_chunk(chunk))


# ── LLM skip decision ─────────────────────────────────────────────────────────

def should_skip_llm(session, fast_response_key: str | None) -> bool:
    """Returns True if LLM should be skipped this turn."""
    if fast_response_key is not None:
        return True
    if session._last_transcript_hash and session._last_transcript_hash in session._seen_transcripts:
        return True
    return False


# ── Message building ──────────────────────────────────────────────────────────

def build_llm_messages(
    session,
    kb_snippet: str | None,
    kb_relevance: float | None = None,
) -> list[dict]:
    """
    Builds the minimal message list for LLM invocation.
    Structure:
      1. System prompt (from active tenant config)
      2. Conversational context compact string (~25 tokens)
      3. Rolling memory summary (every 5 turns, ~20 tokens)
      4. Workflow status (when transactional workflow active)
      5. KB confidence hint (when relevance low)
      6. KB snippet (when available and relevant)
      7. Current user utterance
    """
    from config_loader import get_config
    system_prompt = get_config().context_prompt
    messages: list[dict] = [{"role": "system", "content": system_prompt, "_is_base": True}]

    # Conversational context — domain/intent/goal/repair state
    conv = getattr(session, "conv_context", None)
    if conv:
        ctx_str = conv.to_compact()
        messages.append({"role": "system", "content": f"Context: {ctx_str}"})

    # Rolling memory summary (injected every 5 turns when populated)
    memory = getattr(session, "memory", None)
    if memory and memory.text:
        messages.append({"role": "system", "content": f"Memory: {memory.to_token_str()}"})

    # Workflow status (when transactional workflow active)
    wf = getattr(session, "workflow", None)
    if wf:
        from voice.intent_router import is_valid_person_name
        status_parts = []
        summary = wf.summary.to_text()
        if summary and summary not in ("", "initial"):
            status_parts.append(summary)
        name = wf.entities.get("name")
        if name and is_valid_person_name(name):
            status_parts.append(f"prospect_name={name}")
        email = wf.entities.get("email")
        if email:
            status_parts.append(f"prospect_email={email}")
        if status_parts:
            messages.append({"role": "system", "content": f"Status: {'; '.join(status_parts)}"})

    # KB confidence hint — low relevance signals LLM to be cautious, not confident
    if not kb_snippet or (kb_relevance is not None and kb_relevance < KB_RELEVANCE_THRESHOLD):
        messages.append({
            "role": "system",
            "content": (
                "Knowledge confidence: low. "
                "If uncertain about a specific detail, say so briefly "
                "and offer to connect the visitor with the team."
            ),
        })
    elif kb_snippet and (kb_relevance is None or kb_relevance >= KB_RELEVANCE_THRESHOLD):
        # KB injection — only when relevance is adequate
        clean = process_kb_chunk(kb_snippet)
        if clean:
            messages.append({"role": "system", "content": f"Knowledge: {clean}"})

    # Current user utterance only
    if session._last_transcript:
        messages.append({"role": "user", "content": session._last_transcript})

    return _enforce_token_budget(messages)


def _estimate_tokens(text: str) -> int:
    """Rough token estimate — 4 chars per token."""
    return len(text) // 4


def _enforce_token_budget(messages: list[dict]) -> list[dict]:
    """
    Progressively strips context if over MAX_TOKENS:
    1. Drop KB Context message
    2. Compress summary to just intent
    3. System prompt + current utterance only
    """
    total = sum(_estimate_tokens(m["content"]) for m in messages)
    if total <= MAX_TOKENS:
        return messages

    # Step 1: drop KB context
    messages = [m for m in messages if not m["content"].startswith("Context:")]
    total = sum(_estimate_tokens(m["content"]) for m in messages)
    if total <= MAX_TOKENS:
        return messages

    # Step 2: drop workflow summary
    messages = [m for m in messages if not m["content"].startswith("Status:")]
    total = sum(_estimate_tokens(m["content"]) for m in messages)
    if total <= MAX_TOKENS:
        return messages

    # Step 3: system prompt + user utterance only
    return [m for m in messages if (
        m["role"] == "user"
        or (m["role"] == "system" and m.get("_is_base"))
    )]
