"""
CRM query router — SQL for structured data, RAG for unstructured/history.
Delegates all vector search to knowledge.kb_manager (single canonical path).
"""
import logging
from typing import Any

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

_openai_client: AsyncOpenAI | None = None
_kb_collection: Any = None
_calls_collection: Any = None

STRUCTURED_KEYWORDS = {"order", "account", "phone", "email", "address", "plan", "status"}


def init_crm_query(openai_client: AsyncOpenAI, kb_collection, calls_collection) -> None:
    global _openai_client, _kb_collection, _calls_collection
    _openai_client = openai_client
    _kb_collection = kb_collection
    _calls_collection = calls_collection


async def crm_search(query: str, customer_id: str) -> dict:
    """Natural-language search across KB policies + customer call history."""
    from knowledge.kb_manager import search_kb, search_calls

    kb_hits = await search_kb(query, n_results=2)
    history_hits = await search_calls(query, customer_id, n_results=2)

    all_hits = kb_hits + history_hits
    if not all_hits:
        return {"answer": "No relevant information found.", "sources": [], "hits": []}

    answer_parts = [h["content"] for h in all_hits[:3]]
    sources = [h["source"] for h in all_hits[:3]]
    return {
        "answer": " ".join(answer_parts),
        "sources": sources,
        "hits": all_hits,
    }


async def search_kb_for_context(query: str, n: int = 2) -> list[dict]:
    """
    Quick KB-only pre-fetch used by ws_voice before the agent runs.
    Returns hits with cosine distance < 0.4 only (enforced in kb_manager).
    """
    from knowledge.kb_manager import search_kb
    try:
        return await search_kb(query, n_results=n)
    except Exception as exc:
        logger.warning(f"KB context search error: {exc}")
        return []
