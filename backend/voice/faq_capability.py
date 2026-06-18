"""
FAQ Capability — invoked from any ExecutionMode, never changes mode.

When a customer utterance is likely a factual question about the product, policy,
or procedure, this capability retrieves a RAG answer and returns it as a
context_addition.  The orchestrator injects it as a developer-role message so
the LLM can quote it naturally without the agent remembering it across turns.

Dedup guard: if the top hit has the same doc_id as the previous FAQ injection
(session.orchestrator_state.last_faq_chunk_id), we skip re-injection to avoid
repeating the same answer verbatim in consecutive turns.

FAQ detection is intentionally conservative — precision matters more than recall.
A missed FAQ just means the LLM answers from training data; a false-positive FAQ
in the middle of OTP collection derails the workflow.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING

import httpx
from config import settings

if TYPE_CHECKING:
    from session.call_session import CallSession

logger = logging.getLogger(__name__)

# Base minimum RRF relevance score to surface an answer.
# Set conservatively — a false-positive FAQ during OTP collection pollutes
# the context and causes hallucinations. Better to miss a marginal FAQ hit
# than to inject low-relevance KB content the LLM will treat as facts.
# Follow-up turns use FAQ_FOLLOWUP_THRESHOLD (1.5×) to be even stricter.
FAQ_RELEVANCE_THRESHOLD = 0.20
FAQ_FOLLOWUP_THRESHOLD  = 0.30  # used when last_faq_chunk_id is already set

# Keyword pre-filter: if none of these words appear in the utterance, skip KB lookup
# entirely (saves one async embed call per turn for clearly non-FAQ utterances).
_FAQ_KEYWORDS = frozenset([
    "what", "how", "why", "when", "where", "who", "which",
    "explain", "tell", "describe", "show", "difference",
    "policy", "rule", "can i", "do you", "does wavvy", "is there",
    "refund", "timeline", "time", "process", "fee", "kyc", "document",
    "working", "feature", "support", "works", "mean", "happen",
])


@dataclass
class FAQResult:
    is_faq:     bool
    confidence: float              # 0.0–1.0; RRF relevance score
    answer:     Optional[str]      # RAG-retrieved answer text, if is_faq
    chunk_id:   Optional[str]      # doc_id used for dedup guard; None if not is_faq


async def resolve(text: str, session: "CallSession") -> FAQResult:
    """Try to resolve `text` as a FAQ using the KB.

    Returns FAQResult.is_faq=False immediately if:
    - utterance contains none of the FAQ keywords (fast path)
    - KB returns no results above threshold
    - top hit doc_id matches session.orchestrator_state.last_faq_chunk_id (dedup)

    Never raises — caller must not crash on KB unavailability.
    """
    try:
        lower = text.lower()
        if not any(kw in lower for kw in _FAQ_KEYWORDS):
            return FAQResult(is_faq=False, confidence=0.0, answer=None, chunk_id=None)

        url = f"{settings.backend_internal_url}/api/kb/search"
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(url, params={"q": text, "n": 3})
            resp.raise_for_status()
            hits = resp.json()
        if not hits:
            return FAQResult(is_faq=False, confidence=0.0, answer=None, chunk_id=None)

        state = session.orchestrator_state

        # Apply a stricter threshold on follow-up turns to avoid re-injecting wrong docs
        effective_threshold = (
            FAQ_FOLLOWUP_THRESHOLD if state.last_faq_chunk_id is not None
            else FAQ_RELEVANCE_THRESHOLD
        )

        # Collect all chunks above threshold — do NOT deduplicate by source.
        # Different chunks from the same document often cover different sub-topics
        # (e.g. kyc_verification.md has a "What is KYC" chunk AND a "Documents required"
        # chunk — we need both for a complete answer).
        relevant_chunks: list[dict] = []
        for hit in hits:
            relevance = float(hit.get("relevance") or hit.get("rrf_score") or 0.0)
            if relevance < effective_threshold:
                continue
            src = hit.get("doc_id") or hit.get("source", "")
            relevant_chunks.append({"hit": hit, "relevance": relevance, "src": src})

        if not relevant_chunks:
            top_relevance = float(hits[0].get("relevance") or hits[0].get("rrf_score") or 0.0)
            return FAQResult(is_faq=False, confidence=top_relevance, answer=None, chunk_id=None)

        # Dedup guard — if top chunk already injected last turn, skip
        top_src = relevant_chunks[0]["src"]
        if top_src and top_src == state.last_faq_chunk_id:
            logger.debug("faq_capability: dedup suppressed re-injection of doc_id=%s", top_src)
            return FAQResult(is_faq=False, confidence=relevant_chunks[0]["relevance"], answer=None, chunk_id=None)

        # Build combined answer — join chunks from distinct sources
        parts = []
        for c in relevant_chunks:
            content = c["hit"].get("content", "").strip()
            if content:
                parts.append(content)

        if not parts:
            return FAQResult(is_faq=False, confidence=relevant_chunks[0]["relevance"], answer=None, chunk_id=None)

        combined_answer = "\n\n---\n\n".join(parts)
        top_relevance = relevant_chunks[0]["relevance"]

        logger.debug(
            "faq_capability: FAQ hit relevance=%.3f doc_id=%s (sources: %s)",
            top_relevance, top_src, ", ".join(c["src"] for c in relevant_chunks),
        )
        return FAQResult(is_faq=True, confidence=top_relevance, answer=combined_answer, chunk_id=top_src)

    except Exception:
        logger.exception("faq_capability: error during KB lookup; returning is_faq=False")
        return FAQResult(is_faq=False, confidence=0.0, answer=None, chunk_id=None)
