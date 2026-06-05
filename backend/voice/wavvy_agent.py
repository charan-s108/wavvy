"""
WavvyAgent — LiveKit Agent subclass that applies 5 context-window optimizations
on every LLM call without touching the tool execution path.

Optimizations applied in llm_node() before every OpenAI call:
  1. Stage-gated tools    — only send definitions allowed at current ConversationStage
  2. History compression  — keep last MAX_CONVO_ITEMS user+assistant turns + summary
  3. Stage-aware customer — inject customer profile only at TOOL_EXECUTION / RESOLUTION
  4. RAG on-demand        — KB prefetched while user speaks, injected when relevant
  5. Semantic KB dedup    — skip re-injection when fingerprint matches last turn
"""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from livekit.agents import Agent
from livekit.agents.llm import ChatContext, ChatMessage

if TYPE_CHECKING:
    from livekit.agents.llm import ModelSettings
    from session.call_session import CallSession

logger = logging.getLogger(__name__)

# ── Tunables ──────────────────────────────────────────────────────────────────
MAX_CONVO_ITEMS = 20   # max user+assistant ChatMessages kept per LLM call (~10 exchanges)
KB_MIN_RELEVANCE = 0.015   # RRF scores range ~0.016–0.033 for real hits; filter below this
KB_MAX_CHARS = 1_000       # truncate KB snippet before injection
# escalate_to_human is always available so customers can reach a human from any stage.
# cancel_escalation is NOT always-on — it's only meaningful after escalation fires.
# Keeping it in ALWAYS_ON caused spurious calls during greeting when EOU prediction
# failed and the LLM fired on a single "Hi." with no context.
ALWAYS_ON_TOOLS = {"escalate_to_human"}


class WavvyAgent(Agent):
    """
    Drop-in replacement for Agent. Overrides two hooks:
      on_user_turn_completed — async KB prefetch before LLM fires
      llm_node              — injects optimized context and filtered tools
    """

    def __init__(self, session: CallSession, **kwargs):
        super().__init__(**kwargs)
        self._session = session

    # ── 4. KB prefetch — runs while user finishes speaking ────────────────────

    async def on_user_turn_completed(
        self,
        turn_ctx: ChatContext,
        new_message: ChatMessage,
    ) -> None:
        # Escalated or human taken over — do not prefetch KB or trigger LLM
        if self._session.escalated or self._session.human_joined:
            return
        text = new_message.text_content or ""
        if text.strip():
            # Store task so llm_node can await it if needed
            self._kb_prefetch_task = asyncio.create_task(self._prefetch_kb(text))

    async def _prefetch_kb(self, text: str) -> None:
        # Call FastAPI's /api/kb/search over HTTP — keeps the embedding model
        # out of the worker subprocess (would push RSS past the 512MB limit).
        try:
            import httpx
            from config import settings
            url = f"{settings.backend_internal_url}/api/kb/search"
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(url, params={"q": text, "n": 1})
            if resp.status_code == 200:
                hits = resp.json()
                self._session._pending_kb = hits[0] if hits else None
            else:
                self._session._pending_kb = None
        except Exception as exc:
            logger.debug("[%s] KB prefetch failed: %s", self._session.call_id, exc)
            self._session._pending_kb = None

    # ── Main LLM node — all 5 optimizations applied here ─────────────────────

    async def llm_node(
        self,
        chat_ctx: ChatContext,
        tools: list,
        model_settings,
    ):
        session = self._session

        # Escalated or human taken over — do not invoke the LLM at all.
        # Returning from an async generator produces an empty stream, which the
        # SDK handles gracefully (no TTS, no response).
        if session.escalated or session.human_joined:
            return

        # Wait for in-flight KB prefetch (max 1.5s) before building context.
        # Preemptive generation fires faster than the HTTP search returns;
        # without this await, _pending_kb is always None on quick EOU triggers.
        task = getattr(self, "_kb_prefetch_task", None)
        if task and not task.done():
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=1.5)
            except (asyncio.TimeoutError, Exception):
                pass

        # 1. Stage-gated tools
        filtered_tools = _filter_tools_by_stage(tools, session)

        # 2+3+4+5. Build optimized context copy
        modified_ctx = _build_optimized_context(chat_ctx, session)

        # Yield through the default node — llm_node must be an async generator
        # so the SDK can stream tokens; a plain async def returning the iterable
        # does not compose correctly with the SDK's streaming pipeline.
        async for chunk in Agent.default.llm_node(self, modified_ctx, filtered_tools, model_settings):
            yield chunk


# ── Helper: stage-gated tool filtering ───────────────────────────────────────

def _tool_name(tool) -> str:
    info = getattr(tool, "info", None)
    if info:
        return getattr(info, "name", "") or ""
    return getattr(tool, "name", "") or ""


def _filter_tools_by_stage(tools: list, session: CallSession) -> list:
    """Keep only tool definitions permitted at the session's current stage."""
    try:
        from guardrails.tool_permissions import TOOL_PERMISSIONS
        stage = session.conv_state.stage
        allowed = TOOL_PERMISSIONS.get(stage, set()) | ALWAYS_ON_TOOLS
        filtered = [t for t in tools if _tool_name(t) in allowed]
        if filtered:
            dropped = len(tools) - len(filtered)
            if dropped:
                logger.debug(
                    "[%s] stage=%s — dropped %d tool def(s) from LLM context",
                    session.call_id, stage.value, dropped,
                )
            return filtered
    except Exception as exc:
        logger.debug("[%s] tool stage-filter failed: %s", session.call_id, exc)
    return tools  # fallback: send all


# ── Helper: optimized context builder ────────────────────────────────────────

def _build_optimized_context(chat_ctx: ChatContext, session: CallSession) -> ChatContext:
    """
    Returns a new ChatContext with:
      2. History compressed to MAX_CONVO_ITEMS user+assistant messages
      3. Customer profile injected (only at TOOL_EXECUTION / RESOLUTION)
      2b. Rolling memory summary injected when history was truncated
      4+5. KB snippet injected just before the last user message
    """
    items = list(chat_ctx.items)

    # ── Separate system/instruction messages (always at the top) ──────────────
    # Instructions from Agent() are stored as the first system/developer messages.
    # We keep all leading system messages and compress the rest.
    initial_system: list = []
    rest_start = 0
    for i, item in enumerate(items):
        role = getattr(item, "role", None)
        if isinstance(item, ChatMessage) and role in ("system", "developer"):
            initial_system.append(item)
            rest_start = i + 1
        else:
            break  # first non-system item; convo items start here

    rest_items = items[rest_start:]

    # ── 2. History compression ────────────────────────────────────────────────
    # Walk backwards through rest_items counting user+assistant ChatMessages.
    # Keep all items from the Nth-to-last convo message onward (preserves tool
    # call / output items that sit between messages).
    convo_count = 0
    first_keep_pos = 0  # index within rest_items to start keeping
    truncated = False
    for i in range(len(rest_items) - 1, -1, -1):
        item = rest_items[i]
        if isinstance(item, ChatMessage) and item.role in ("user", "assistant"):
            convo_count += 1
            if convo_count >= MAX_CONVO_ITEMS:
                first_keep_pos = i
                truncated = True
                break

    recent_items = rest_items[first_keep_pos:]

    # ── Build injected system messages ────────────────────────────────────────
    injections: list = []

    # 3. Customer context — only at transactional stages
    customer_msg = _build_customer_msg(session)
    if customer_msg:
        injections.append(customer_msg)

    # 2b. Memory summary — only when history was truncated
    if truncated:
        memory = getattr(session, "memory", None)
        if memory and getattr(memory, "text", None):
            injections.append(ChatMessage(
                role="system",
                content=[f"Earlier conversation summary: {memory.text[:180]}"],
            ))

    # 4+5. KB snippet
    kb_msg = _build_kb_msg(session)

    # ── Assemble final items ──────────────────────────────────────────────────
    # Order: instructions → injections → recent convo (KB before last user msg)
    new_items: list = list(initial_system) + injections

    if kb_msg and recent_items:
        # Find the last user message within recent_items
        last_user_pos = len(recent_items)  # default: append KB at end
        for j in range(len(recent_items) - 1, -1, -1):
            if isinstance(recent_items[j], ChatMessage) and recent_items[j].role == "user":
                last_user_pos = j
                break
        new_items.extend(recent_items[:last_user_pos])
        new_items.append(kb_msg)
        new_items.extend(recent_items[last_user_pos:])
    else:
        new_items.extend(recent_items)

    return ChatContext(items=new_items)


def _build_customer_msg(session: CallSession) -> ChatMessage | None:
    """Inject a minimal customer profile at TOOL_EXECUTION and RESOLUTION stages."""
    try:
        from session.conversation_state import ConversationStage
        stage = session.conv_state.stage
        if stage not in (ConversationStage.TOOL_EXECUTION, ConversationStage.RESOLUTION):
            return None
        profile = getattr(session, "customer_profile", None) or {}
        if not profile:
            return None
        name = profile.get("first_name") or profile.get("name", "")
        acct = profile.get("account_type", "standard")
        txns = profile.get("transactions") or []
        txn_ids = ", ".join(str(t.get("txn_number", "")) for t in txns[:5] if t.get("txn_number"))
        otp_status = "OTP verified" if session.otp_verified else "OTP not verified"
        masked_email = profile.get("masked_email", "")
        masked_phone = profile.get("masked_phone", "")
        parts = [f"Customer: {name} ({acct} account). {otp_status}."]
        if masked_email:
            parts.append(f"Email on file: {masked_email} (partial — cannot be read aloud in full).")
        if masked_phone:
            parts.append(f"Phone on file: {masked_phone} (partial).")
        if txn_ids:
            parts.append(f"Transactions: {txn_ids}.")
        return ChatMessage(role="system", content=[" ".join(parts)])
    except Exception:
        return None


def _build_kb_msg(session: CallSession) -> ChatMessage | None:
    """Return a KB system message if the pending hit is relevant and not a duplicate."""
    pending = getattr(session, "_pending_kb", None)
    if not pending:
        return None

    # Consume immediately — each KB hit is injected at most once
    session._pending_kb = None

    relevance = pending.get("relevance") or pending.get("rrf_score") or 0
    if relevance < KB_MIN_RELEVANCE:
        return None

    content = (pending.get("content") or "")[:KB_MAX_CHARS].strip()
    source = pending.get("source", "")
    if not content:
        return None

    # 5. Semantic dedup via ConversationalContext KB fingerprint cache
    try:
        conv = getattr(session, "conv_context", None)
        if conv:
            cached = conv.get_cached_kb(
                conv.conversation_domain,
                conv.conversation_intent,
                conv.active_entities,
            )
            if cached and cached[:120] == content[:120]:
                return None  # same chunk served last turn — skip
            conv.store_kb_result(
                content,
                conv.conversation_domain,
                conv.conversation_intent,
                conv.active_entities,
            )
    except Exception:
        pass

    return ChatMessage(role="system", content=[f"Policy [{source}]: {content}"])
