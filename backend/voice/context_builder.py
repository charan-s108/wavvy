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


# ── Orchestrator-aware context builder ────────────────────────────────────────

def build_orchestrated_context(chat_ctx, decision, session) -> "ChatContext":
    """Build a ChatContext that incorporates an OrchestratorDecision.

    Wraps the existing _build_optimized_context from wavvy_agent (imported
    at call time to avoid circular imports) and layers orchestrator additions:

    1. Agent persona override — if decision.agent_profile_override is set,
       append its persona to the first system message.
    2. Node directive — injected as a developer-role message when set.
    3. Context additions — FAQ answer or auto-action results from the decision;
       each is a dict {role, content} converted to ChatMessage.

    Returns a new ChatContext; the input chat_ctx is not mutated.
    """
    from livekit.agents.llm import ChatContext as _ChatContext, ChatMessage as _ChatMessage

    # Use the existing optimized-context builder as the base
    try:
        from voice.wavvy_agent import _build_optimized_context
        base_ctx = _build_optimized_context(chat_ctx, session)
    except Exception:
        logger.exception("build_orchestrated_context: _build_optimized_context failed; using raw")
        base_ctx = chat_ctx

    items = list(base_ctx.items)

    # 0. Verification history compression — when verify_otp just succeeded, replace
    # the phone-number and OTP turns with a single clean identity-confirmed message.
    # This removes raw digits from context so the LLM can't recycle them as TXN IDs.
    if getattr(decision, "compress_verification_history", False):
        items = _compress_verification_turns(items, session)

    # 1. Agent persona override: append persona to first system message
    agent_profile = getattr(decision, "agent_profile_override", None)
    if agent_profile and getattr(agent_profile, "persona", None):
        for i, item in enumerate(items):
            if isinstance(item, _ChatMessage) and item.role in ("system", "developer"):
                old_text = item.text_content or ""
                items[i] = _ChatMessage(
                    role=item.role,
                    content=[old_text + f"\n\n[Persona note]: {agent_profile.persona}"],
                )
                break

    # 2+3. Directive + context additions — inject just before the last user message
    inject: list[_ChatMessage] = []

    # Customer profile: re-inject on EVERY turn after verification so the LLM always
    # sees the account state (KYC status, problematic transactions, holds) regardless
    # of which turn verify_account originally fired.  Without this, the [Customer
    # Verified] block is only visible on the verification turn and is invisible to the
    # LLM at issue_discovery time — causing it to answer "what can I help you with?"
    # instead of "I can see your TXN-5512 is on KYC hold".
    customer_profile = getattr(session, "customer_profile", None)
    if customer_profile:
        try:
            from workflow.node_executor import _build_customer_context_message
            inject.append(_ChatMessage(
                role="developer",
                content=[_build_customer_context_message(customer_profile)],
            ))
        except Exception:
            logger.exception("context_builder: failed to inject customer profile")

    directive = getattr(decision, "directive", "") or ""
    if directive:
        inject.append(_ChatMessage(
            role="developer",
            content=[f"[Directive]: {directive}"],
        ))

    for addition in (getattr(decision, "context_additions", None) or []):
        role    = addition.get("role", "developer")
        content = addition.get("content", "")
        if content:
            inject.append(_ChatMessage(role=role, content=[content]))

    if inject:
        # Find last user message position
        last_user_pos = len(items)
        for j in range(len(items) - 1, -1, -1):
            if isinstance(items[j], _ChatMessage) and items[j].role == "user":
                last_user_pos = j
                break
        # Insert injections immediately before the last user message
        items = items[:last_user_pos] + inject + items[last_user_pos:]

    return _ChatContext(items=items)


def _compress_verification_turns(items: list, session) -> list:
    """Replace the phone-number and OTP exchange with a single identity-confirmed message.

    Scans backwards through items and collapses the last 4–6 turns that formed the
    verification exchange (phone ask, phone digits, OTP ask, OTP digits) into one
    synthetic assistant message.  System/developer messages are preserved; only
    user and assistant turns from the verification exchange are replaced.

    This prevents raw phone digits and OTP codes from persisting in context where
    the LLM might mistake them for transaction references or other identifiers.
    """
    try:
        from livekit.agents.llm import ChatMessage as _ChatMessage

        profile = getattr(session, "customer_profile", None) or {}
        full_name = profile.get("name") or "the customer"
        first_name = (profile.get("first_name") or full_name.split()[0]) if full_name else "there"

        # Find the last user message (OTP digits turn) and walk back to capture
        # all verification turns — typically: phone-ask, phone-digits, otp-ask, otp-digits
        # We remove up to 6 user+assistant messages from the end of history (but
        # never touch system/developer messages or messages before the last 10).
        result = list(items)
        user_and_assistant = [
            i for i, m in enumerate(result)
            if isinstance(m, _ChatMessage) and m.role in ("user", "assistant")
        ]
        # Keep at least the first system messages; only compress recent turns
        if len(user_and_assistant) < 2:
            return result

        # Remove the last 4 user+assistant turns (phone + OTP exchange) and replace
        # with a single clean assistant summary.
        turns_to_remove = user_and_assistant[-4:]   # phone-digits + otp-digits + their agent responses
        keep_indices = set(range(len(result))) - set(turns_to_remove)
        compressed = [m for i, m in enumerate(result) if i in keep_indices]

        # Inject the summary at the position where the first removed turn was
        insert_at = min(turns_to_remove)
        summary = _ChatMessage(
            role="assistant",
            content=[f"I've verified your identity, {first_name}. You're all set, {first_name} — how can I help you today?"],
        )
        compressed = compressed[:insert_at] + [summary] + compressed[insert_at:]
        logger.debug(
            "context_builder: compressed verification exchange (%d turns → 1 summary) for %s",
            len(turns_to_remove), first_name,
        )
        return compressed
    except Exception:
        logger.exception("context_builder: _compress_verification_turns failed; returning original")
        return items
